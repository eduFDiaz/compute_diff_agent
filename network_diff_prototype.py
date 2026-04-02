from __future__ import annotations

import argparse
import logging
import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Literal, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI


def _configure_run_logging(log_dir: Path | None = None) -> logging.Logger:
    base_dir = Path(__file__).resolve().parent
    log_dir = log_dir or (base_dir / "logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pid = os.getpid()
    log_path = log_dir / f"run_{timestamp}_{pid}.log"

    logger = logging.getLogger("network_diff_prototype")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # Ensure reruns in the same interpreter/session don't duplicate handlers.
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    logger.info("Log file: %s", log_path)
    return logger


# -----------------------------
# Models for structured output
# -----------------------------
class ConfigChange(BaseModel):
    path: str = Field(description="Hierarchical location in the config, e.g. 'interface GigabitEthernet0/0'")
    operation: Literal["add", "remove", "replace"]
    field: str = Field(description="Normalized field name, e.g. ip_address, access_vlan, cvlan")
    before: Optional[str] = None
    after: Optional[str] = None
    reason: Optional[str] = None


class ConfigDiff(BaseModel):
    vendor: str
    summary: str
    changes: List[ConfigChange] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class CommandOutput(BaseModel):
    summary: str
    commands: List[str] = Field(default_factory=list)
    apply_config: Optional[str] = Field(
        default=None,
        description="Paste-ready configuration snippet to apply sequentially on the device.",
    )
    rollback: List[str] = Field(default_factory=list)
    rollback_config: Optional[str] = Field(
        default=None,
        description="Paste-ready configuration snippet to rollback the changes.",
    )
    warnings: List[str] = Field(default_factory=list)


# -----------------------------
# LLM wrapper
# -----------------------------
PROVIDERS = ("openai", "ollama")


class NetworkDiffPrototype:
    def __init__(
        self,
        model: str | None = None,
        temperature: float = 0.0,
        provider: str = "openai",
    ) -> None:
        if provider not in PROVIDERS:
            raise ValueError(f"provider must be one of {PROVIDERS}, got {provider!r}")

        load_dotenv()

        if provider == "ollama":
            _model = model or "phi4-mini"
            self.llm = ChatOllama(
                model=_model,
                temperature=temperature,
            )
        else:
            _model = model or "gpt-4.1-mini"
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise RuntimeError("OPENAI_API_KEY is not set.")
            self.llm = ChatOpenAI(
                model=_model,
                temperature=temperature,
                api_key=api_key,
            )

        # First pass returns a typed diff object
        self.diff_llm = self.llm.with_structured_output(ConfigDiff)

        # Second pass returns typed command output
        self.command_llm = self.llm.with_structured_output(CommandOutput)

    def build_diff(self, vendor: str, config_1: str, config_2: str) -> ConfigDiff:
        prompt = f"""
You are a senior network configuration diff engine.

Goal:
Compare CONFIG_1 (current state) with CONFIG_2 (target state) and produce a semantic diff.

Vendor/platform:
{vendor}

Instructions:
- Compare semantically, not as a raw text diff.
- Ignore whitespace-only differences, comments, and harmless formatting changes.
- Ignore ordering differences unless order changes semantics.
- Do not invent configuration that is not present.
- Only include meaningful state changes required to transform CONFIG_1 into CONFIG_2.
- Use normalized field names such as:
  - ip_address
  - secondary_ip_address
  - access_vlan
  - trunk_allowed_vlans
  - cvlan
  - description
  - shutdown_state
  - encapsulation
  - vrf
- Use precise paths such as:
  - interface GigabitEthernet0/0
  - interface GigabitEthernet0/0 service instance 10 ethernet
  - vlan 200
  - router bgp 65000 neighbor 1.1.1.1
- Be conservative. If something is ambiguous, mention it in warnings.

CONFIG_1:
<<<CONFIG_1
{config_1}
CONFIG_1

CONFIG_2:
<<<CONFIG_2
{config_2}
CONFIG_2
"""
        return self.diff_llm.invoke(prompt)

    def generate_commands(self, vendor: str, diff: ConfigDiff) -> CommandOutput:
        prompt = f"""
You are a senior network engineer.

Goal:
Generate the minimal CLI commands required to transform the current config into the target config.

Vendor/platform:
{vendor}

Structured semantic diff:
{diff.model_dump_json(indent=2)}

Rules:
- Only generate commands for the listed changes.
- Preserve everything not mentioned in the diff.
- Use vendor-correct syntax.
- Prefer the smallest safe command set.
- When replacing values, remove old values first if the platform typically requires it.
- Do not include save/write commands unless needed for correctness.
- Do not invent interface names, VLANs, or values not present in the diff.
- Rollback should reverse only the produced commands as much as possible.

Output requirements:
- `commands`: a flat list of CLI lines in the correct order.
- `apply_config`: a single multi-line snippet that is safe to paste and run sequentially on the device.
    - Include required mode transitions for the vendor (e.g., enter/exit interface context).
    - If the vendor typically uses a global config mode, include entering/exiting it.
    - Keep it minimal and deterministic; no interactive prompts.
- `rollback`: a flat list of rollback CLI lines in the correct order.
- `rollback_config`: a single multi-line snippet to rollback sequentially (same rules as apply_config).
"""
        output: CommandOutput = self.command_llm.invoke(prompt)

        # Make these always available for downstream consumers/logging, even if the model
        # forgets to populate them.
        apply_config = (output.apply_config or "").strip() or "\n".join(output.commands)
        rollback_config = (output.rollback_config or "").strip() or "\n".join(output.rollback)

        if apply_config != output.apply_config or rollback_config != output.rollback_config:
            output = output.model_copy(
                update={
                    "apply_config": apply_config,
                    "rollback_config": rollback_config,
                }
            )

        return output

    def validate_result(self, diff: ConfigDiff, commands: CommandOutput) -> List[str]:
        """
        Lightweight local validation. This is not a syntax validator.
        It just checks whether important target values from the diff appear somewhere
        in the generated commands.
        """
        errors: List[str] = []
        cmd_blob = "\n".join(commands.commands)

        for change in diff.changes:
            if change.after and change.after not in cmd_blob:
                # Not every semantic value will appear literally, but this is useful for an MVP.
                errors.append(
                    f"Target value may be missing from commands: field={change.field}, after={change.after}, path={change.path}"
                )

        return errors

    def run(self, vendor: str, config_1: str, config_2: str) -> dict:
        diff = self.build_diff(vendor, config_1, config_2)
        command_output = self.generate_commands(vendor, diff)
        validation_errors = self.validate_result(diff, command_output)

        return {
            "diff": diff.model_dump(),
            "commands": command_output.model_dump(),
            "validation_errors": validation_errors,
        }


# -----------------------------
# Example usage
# -----------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute a semantic diff between two network configs.")
    parser.add_argument("config1", type=Path, help="Path to the current config file (CONFIG_1).")
    parser.add_argument("config2", type=Path, help="Path to the target config file (CONFIG_2).")
    parser.add_argument("--vendor", default="ekinops_one621", help="Vendor/platform string (default: ekinops_one621).")
    parser.add_argument(
        "--provider",
        choices=PROVIDERS,
        default="openai",
        help="LLM provider: 'openai' (default) or 'ollama' (local, uses phi4-mini by default).",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model name override. Defaults: openai=gpt-4.1-mini, ollama=phi4-mini.",
    )
    args = parser.parse_args()

    logger = _configure_run_logging()

    config_1 = Path(args.config1).read_text(encoding="utf-8").strip()
    config_2 = Path(args.config2).read_text(encoding="utf-8").strip()

    try:
        app = NetworkDiffPrototype(
            model=args.model,
            temperature=0.0,
            provider=args.provider,
        )

        result = app.run(
            vendor=args.vendor,
            config_1=config_1,
            config_2=config_2,
        )

        logger.info("Vendor: %s", args.vendor)

        logger.info("=== CONFIG 1 ===\n%s", config_1)
        logger.info("=== CONFIG 2 ===\n%s", config_2)
        logger.info("=== DIFF ===\n%s", json.dumps(result["diff"], indent=2))
        logger.info("=== COMMANDS ===\n%s", json.dumps(result["commands"], indent=2))

        apply_config = (result.get("commands") or {}).get("apply_config")
        rollback_config = (result.get("commands") or {}).get("rollback_config")

        if apply_config:
            logger.info("=== APPLY CONFIG (PASTE-READY) ===\n%s", apply_config)
        if rollback_config:
            logger.info("=== ROLLBACK CONFIG (PASTE-READY) ===\n%s", rollback_config)
        logger.info(
            "=== VALIDATION ERRORS ===\n%s",
            json.dumps(result["validation_errors"], indent=2),
        )
    except (ValidationError, Exception):
        logger.exception("Run failed")
        raise
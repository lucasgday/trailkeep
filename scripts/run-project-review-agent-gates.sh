#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/run-project-review-agent-gates.sh [global options] <command> [command options]

Global options:
  --trailkeep-repo DIR   trailkeep repo path. Defaults to this script's repo.
  --skill-dir DIR        trailkeep-project-review skill path. Defaults to the repo skill.
  --python BIN           Python binary. Defaults to python3.

Commands:
  pre        Run the mandatory pre-model gate.
             Passes options through to pre_model_gate.py, usually:
             --backup-dir <backup_dir>

  repo-sync  Run the optional repo freshness check after pre passes.
             Passes options through to check_repo_sync.py, usually:
             --backup-dir <backup_dir>

  validate-summary
            Validate one generated conversation summary before checkpointing it.
             Passes options through to validate_conversation_summary.py, usually:
             --summary-json <path-or-> --session-id <id>

  prepare-test
            Prepare an isolated project-scoped review test sandbox.
             Copies/scopes deterministic sidecars, links selected markdowns,
             runs planner eval + pre gate inside the sandbox, and writes a
             project-review-test-prompt.txt file.
             Usually: --backup-dir <backup_dir> --project <project_name>

  finalize   Run generated-output evals and write the review update log.
             Passes options through to finalize_review_run.py, usually:
             --backup-dir <backup_dir> --model-provider <provider>
             --model-routing <available|unavailable> --model-used <model>

Examples:
  scripts/run-project-review-agent-gates.sh pre --backup-dir /path/to/backups
  scripts/run-project-review-agent-gates.sh repo-sync --backup-dir /path/to/backups
  scripts/run-project-review-agent-gates.sh validate-summary --summary-json /tmp/summary.json
  scripts/run-project-review-agent-gates.sh prepare-test --backup-dir /path/to/backups --project agentlog
  scripts/run-project-review-agent-gates.sh finalize --backup-dir /path/to/backups --model-used gpt-5
USAGE
}

die() {
  echo "run-project-review-agent-gates.sh: $*" >&2
  exit 2
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_TRAILKEEP_REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
TRAILKEEP_REPO="${TRAILKEEP_REPO_DIR:-$DEFAULT_TRAILKEEP_REPO}"
SKILL_DIR="${TRAILKEEP_REVIEW_SKILL_DIR:-$TRAILKEEP_REPO/skills/trailkeep-project-review}"
PYTHON_BIN="${PYTHON:-python3}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --trailkeep-repo)
      [[ $# -ge 2 ]] || die "--trailkeep-repo requires a path"
      TRAILKEEP_REPO="$2"
      shift 2
      ;;
    --skill-dir)
      [[ $# -ge 2 ]] || die "--skill-dir requires a path"
      SKILL_DIR="$2"
      shift 2
      ;;
    --python)
      [[ $# -ge 2 ]] || die "--python requires a binary"
      PYTHON_BIN="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      break
      ;;
  esac
done

[[ $# -ge 1 ]] || { usage >&2; exit 2; }

COMMAND="$1"
shift

TRAILKEEP_REPO="$(cd "$TRAILKEEP_REPO" && pwd)" || die "trailkeep repo does not exist: $TRAILKEEP_REPO"
SKILL_DIR="$(cd "$SKILL_DIR" && pwd)" || die "skill dir does not exist: $SKILL_DIR"

case "$COMMAND" in
  pre|gate)
    SCRIPT="$SKILL_DIR/scripts/pre_model_gate.py"
    [[ -f "$SCRIPT" ]] || die "missing pre-model gate script: $SCRIPT"
    exec "$PYTHON_BIN" "$SCRIPT" "$@"
    ;;
  repo-sync|sync)
    SCRIPT="$SKILL_DIR/scripts/check_repo_sync.py"
    [[ -f "$SCRIPT" ]] || die "missing repo sync script: $SCRIPT"
    exec "$PYTHON_BIN" "$SCRIPT" "$@"
    ;;
  validate-summary|summary)
    SCRIPT="$SKILL_DIR/scripts/validate_conversation_summary.py"
    [[ -f "$SCRIPT" ]] || die "missing conversation summary validator script: $SCRIPT"
    exec "$PYTHON_BIN" "$SCRIPT" "$@"
    ;;
  prepare-test|test)
    SCRIPT="$SKILL_DIR/scripts/prepare_review_test.py"
    [[ -f "$SCRIPT" ]] || die "missing review test preparation script: $SCRIPT"
    exec "$PYTHON_BIN" "$SCRIPT" --trailkeep-repo "$TRAILKEEP_REPO" --skill-dir "$SKILL_DIR" "$@"
    ;;
  finalize|post)
    SCRIPT="$SKILL_DIR/scripts/finalize_review_run.py"
    [[ -f "$SCRIPT" ]] || die "missing finalizer script: $SCRIPT"
    exec "$PYTHON_BIN" "$SCRIPT" --trailkeep-repo "$TRAILKEEP_REPO" "$@"
    ;;
  *)
    usage >&2
    die "unknown command: $COMMAND"
    ;;
esac

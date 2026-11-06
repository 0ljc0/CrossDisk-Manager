"""Linux bundle preflight, or explicit execution on an apply-enabled loop test root."""
import argparse
import json
import subprocess

from app.services.linux_preflight import preflight
from app.services.linux_execution import apply


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--target", required=True)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--dry-run", action="store_true")
    modes.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-uuid")
    parser.add_argument("--confirm-maintenance-window", action="store_true")
    args = parser.parse_args()
    if args.apply and (not args.confirm_uuid or not args.confirm_maintenance_window):
        parser.error("--apply requires --confirm-uuid and --confirm-maintenance-window")
    if not args.apply and (args.confirm_uuid or args.confirm_maintenance_window):
        parser.error("Confirmation arguments are only valid with --apply")
    try:
        report = apply(args.bundle, args.target, args.confirm_uuid) if args.apply else preflight(args.bundle, args.target)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        report = dict(status="NEEDS_RECOVERY" if args.apply else "PREFLIGHT_REJECTED", error=str(exc),
                      apply_allowed=False, target_modified=None if args.apply else False)
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report["status"] in ("PREFLIGHT_OK", "COMPLETED", "ROLLED_BACK") else 1


if __name__ == "__main__":
    raise SystemExit(main())

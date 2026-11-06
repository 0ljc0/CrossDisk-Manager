"""Inspect, explicitly continue or roll back a registered loop-image execution."""
import argparse
import json
import subprocess
from app.services.linux_execution import recover


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target",required=True)
    parser.add_argument("--bundle-id",required=True)
    modes=parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check",action="store_true")
    modes.add_argument("--resume",action="store_true")
    modes.add_argument("--rollback",action="store_true")
    parser.add_argument("--confirm-plan")
    parser.add_argument("--confirm-uuid")
    parser.add_argument("--confirm-maintenance-window",action="store_true")
    args=parser.parse_args()
    if not args.check and not (args.confirm_plan and args.confirm_uuid and args.confirm_maintenance_window):
        parser.error("Recovery writes require plan, UUID and maintenance-window confirmation")
    if args.check and (args.confirm_plan or args.confirm_uuid or args.confirm_maintenance_window):
        parser.error("--check takes no write confirmations")
    try:
        value=recover(args.target,args.bundle_id,action="check" if args.check else "resume" if args.resume else "rollback",
                      confirm_uuid=args.confirm_uuid,confirm_plan=args.confirm_plan)
        print(json.dumps(value,ensure_ascii=True,indent=2))
        return 1 if any(o["result"]=="UNKNOWN" for o in value["observations"]) else 0
    except (OSError,ValueError,TypeError,KeyError,subprocess.SubprocessError) as exc:
        print(json.dumps(dict(status="NEEDS_MANUAL_REVIEW",error=str(exc))))
        return 1


if __name__=="__main__":raise SystemExit(main())

"""Register an existing, explicitly confirmed Linux test root (preflight only)."""
import argparse
import json
import subprocess

from app.services.linux_registry import policy, register


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("--mount-point", required=True)
    parser.add_argument("--relative-root", required=True)
    parser.add_argument("--state-root", required=True)
    parser.add_argument("--backup-root", required=True)
    parser.add_argument("--allow-uid", type=int, action="append", required=True)
    parser.add_argument("--allow-gid", type=int, action="append", required=True)
    parser.add_argument("--file-mode", type=lambda s: int(s, 8), action="append")
    parser.add_argument("--directory-mode", type=lambda s: int(s, 8), action="append")
    parser.add_argument("--confirm-test-root", required=True)
    parser.add_argument("--confirm-uuid", required=True)
    parser.add_argument("--initialize", action="store_true")
    parser.add_argument("--enable-bundle-apply", action="store_true",
                        help="Authorize bundle execution on a registered loop test image only")
    args = parser.parse_args()
    try:
        allowed = policy(args.allow_uid, args.allow_gid, args.file_mode or [0o600, 0o644],
                         args.directory_mode or [0o700, 0o755])
        entry = register(args.name, args.mount_point, args.relative_root, args.state_root,
                         args.backup_root, allowed, args.confirm_test_root, args.confirm_uuid,
                         initialize=args.initialize, enable_bundle_apply=args.enable_bundle_apply)
        print(json.dumps(dict(registered=True, name=entry["name"], target_key=entry["target_key"],
                              purpose=entry["purpose"], apply_allowed=False), indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(json.dumps(dict(registered=False, error=str(exc), apply_allowed=False)))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

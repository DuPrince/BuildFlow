# modules/notify/ic_cli.py
# -*- coding: utf-8 -*-

import argparse
import logging
from modules.notify.ic_util import send_to_group, send_to_user


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    parser = argparse.ArgumentParser("ic_cli")

    parser.add_argument("--group", help="IGGChat group name")
    parser.add_argument("--tittle", help="IGGChat message tittle")
    parser.add_argument("--user", required=True, help="IGGChat user name")
    parser.add_argument("--token", required=True, help="IGGChat msg token")
    parser.add_argument("--message", required=True, help="message content")

    args = parser.parse_args()

    if args.group:
        send_to_group(args.token, args.message, args.group,
                      at_user=args.user, title=args.tittle)
    elif args.user:
        send_to_user(args.token, args.user, args.message, title=args.tittle)
    else:
        logging.error("Either --group or --user must be specified.")


if __name__ == "__main__":
    main()

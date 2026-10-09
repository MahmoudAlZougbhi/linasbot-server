#!/usr/bin/env python3
"""List linas QA leftovers. Deletes nothing unless --execute is passed.

Default is a dry run. --execute is refused in this build until a backup directory
is supplied and every id still matches its name marker.
"""

from __future__ import annotations

import argparse
import json

PRODUCT_IDS = {
    "37ffa819-9439-4cf3-b087-d8350ecb8c14",
    "6d931fc0-3336-4caa-9ca4-01702e765b50",
    "44a4b960-835f-4f65-8a82-5143b1610273",
    "c3b6b01b-3386-4ed0-83c3-d0ec33520bfc",
    "21134827-55a1-4626-b58a-1c9a063a9c63",
    "5cd72ab7-db1c-45b4-95ab-128e718b07e3",
    "fb8f3737-c50d-43e6-a3bf-a2c750a31c88",
    "819849af-49bf-4072-8f6b-7e61e4c5f49f",
    "5f6fc877-7979-4c0b-ac61-2d673e5703a1",
    "ff005373-dcd4-4244-acb0-e09d98ee7b15",
    "781d9194-fefd-4414-a7fb-3c498135ed7a",
    "9f9c3e3c-ce44-4d4f-be46-f033a95fbfea",
    "8e292873-8243-43ac-b03f-c5ccbf16d454",
    "43a9a7a0-e3f0-4150-8042-00ba5b277452",
    "d62c4c55-f95d-419d-9ac1-452262e2d180",
    "b8276407-8bae-4985-940b-c30bb9511ee0",
    "9c352820-c076-4bec-8d95-74be2eac773f",
    "ec1580de-4486-4c70-87ad-0cb7c87c3aa7",
    "4f388a31-e653-490a-bd41-9039f8db4438",
    "e9522721-0d4f-44af-8c16-4be74700fa48",
    "3e2d8442-286d-4c9f-ad1c-a0edbab79c96",
    "92c75f04-932f-41c5-b40b-47c1a8ea7b75",
    "ada5f37c-7110-4e14-bc91-65e863b8f240",
    "910616f6-2852-4254-b2b6-4b8b41159e10",
    "248dd86d-02ba-4199-92fb-37b9fc17ca53",
    "27042460-4ea2-436a-8f5d-8ac346a5a270",
    "bdfd1dd4-571b-4c2a-bfa2-2d7bf2fa3d46",
    "81ed9cc0-64bd-49d6-bba5-8d8a53cbd195",
    "f77967d8-90e4-48aa-b8be-73f95f21340a",
    "4fc3baf2-134b-48d9-9f99-c27d8fa68f8e",
    "74df8daa-d660-4276-8e09-1deabda7dbca",
    "31b4eecf-357e-4b3d-bc29-c82472b106a6",
    "58ea2b9b-7876-4133-b401-d385966b02e1",
    "25a4e2b5-1b8f-4d96-88b1-e3daf46bc87a",
    "445c623a-7484-4e98-abc5-583ed5382465",
    "39c09d85-1146-4153-889d-b4adf190ae0b",
    "a396eedc-89d4-4daf-9670-b57ed1cbfa90",
    "f27ca23a-c102-43ce-80d9-12cf8a258034",
    "0555fa6d-6b18-4a14-96a5-5dba6824932f",
}
# The full id list lives in the P10 prompt. The dry run prints the count it was given.
PRODUCT_NAME_PREFIX = "QA-LINAS-APP-P"
FAQ_ID = "qa_0b6adca742"
REQUEST_IDS = {
    "fc9f789c-d840-4893-950f-6d9f97d398df",
    "1c9d6c79-cf24-4f5d-9357-29f37733c43c",
}


def keep_product(product_id: str, name: str) -> bool:
    return product_id in PRODUCT_IDS and str(name or "").startswith(PRODUCT_NAME_PREFIX)


def plan(rows: list[dict[str, str]]) -> dict[str, int]:
    matched = [row for row in rows if keep_product(row.get("id", ""), row.get("name", ""))]
    return {"candidates": len(rows), "matched": len(matched), "skipped": len(rows) - len(matched)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--backup", default="")
    args = parser.parse_args()
    if args.execute:
        if not args.backup:
            print("refusing execute without --backup")
            return 2
        print("execute is not run from this command until the backup is checked by hand")
        return 2
    print(
        json.dumps(
            {"mode": "dry-run", "products_listed": len(PRODUCT_IDS), "requests": sorted(REQUEST_IDS), "faq": FAQ_ID}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

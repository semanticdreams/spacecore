"""Exact, idempotent failure-propagation patch for pinned public-domain 3.9.

The private lookup API must never disclose inspection failure as a negative.
No grammar, matching order, label, policy or system-installed file is changed.
"""
import hashlib
from pathlib import Path
import sys

PATCHES = {
    "label_file.c": (
        "f2bc93e276a35a2d4c9b1dd49afd17f4e2a59831fdc784ce0b57b2eb9e20a9bf",
        [
            ("\t\t\t\t\t   rspec->regex_str, errbuf);\n\t\t\t\tgoto fail;",
             "\t\t\t\t\t   rspec->regex_str, errbuf);\n\t\t\t\terrno = EIO;\n\t\t\t\tgoto fail;"),
            ("\t\t\t/* else it's an error */\n\t\t\terrno = ENOENT;",
             "\t\t\t/* Inspection failure is not a negative match. */\n\t\t\terrno = EIO;"),
            ("\t\trc = stat(path, &fdetails[i].sb);\n\t\tif (rc)\n\t\t\tcontinue;",
             "\t\trc = stat(path, &fdetails[i].sb);\n\t\tif (rc) {\n\t\t\tif (errno == ENOENT) continue;\n\t\t\treturn NULL;\n\t\t}"),
            ("\tmemcpy(sb, &found->sb, sizeof(*sb));\n\treturn fopen(save_path, \"re\");",
             "\tmemcpy(sb, &found->sb, sizeof(*sb));\n\tFILE *fp = fopen(save_path, \"re\");\n\tif (!fp && errno == ENOENT) errno = EIO;\n\treturn fp;"),
            ("\t\tif (rc < 0) {\n\t\t\tfclose_errno_safe(fp);\n\t\t\treturn -1;\n\t\t}",
             "\t\tif (rc < 0) {\n\t\t\tfclose_errno_safe(fp);\n\t\t\terrno = EIO;\n\t\t\treturn -1;\n\t\t}"),
            ("\t}\n\treturn -1;\n}\n\nstatic void selabel_subs_fini",
             "\t}\n\terrno = EIO;\n\treturn -1;\n}\n\nstatic void selabel_subs_fini"),
            ("\trc = 0;\nout:\n\tfree(line_buf);",
             "\trc = feof(fp) ? 0 : -1;\n\tif (rc) errno = EIO;\nout:\n\tfree(line_buf);"),
            ("\tsize_t len = fread(&magic, sizeof(magic), 1, fp);\n",
             "\tsize_t len = fread(&magic, sizeof(magic), 1, fp);\n\tif (ferror(fp)) { errno = EIO; return -1; }\n"),
            ("\trc = fstat(fileno(cfg), &sb);",
             "\tif (!feof(cfg)) { errno = EIO; goto err; }\n\trc = fstat(fileno(cfg), &sb);"),
            ("\tptr = selabel_apply_subs(data->subs, data->subs_num, key, key_len);\n\tif (ptr) {\n\t\tdptr = selabel_apply_subs(data->dist_subs, data->dist_subs_num, ptr, strlen(ptr));\n\t\tif (dptr) {",
             "\terrno = 0;\n\tptr = selabel_apply_subs(data->subs, data->subs_num, key, key_len);\n\tif (!ptr && errno) return NULL;\n\tif (ptr) {\n\t\terrno = 0;\n\t\tdptr = selabel_apply_subs(data->dist_subs, data->dist_subs_num, ptr, strlen(ptr));\n\t\tif (!dptr && errno) { free(ptr); return NULL; }\n\t\tif (dptr) {"),
            ("\tsub = selabel_sub_key(data, key, len);\n\tif (sub)\n\t\tkey = sub;",
             "\terrno = 0;\n\tsub = selabel_sub_key(data, key, len);\n\tif (sub)\n\t\tkey = sub;\n\telse if (errno)\n\t\tgoto finish;"),
        ],
    ),
    "label.c": (
        "e98ece15f3e9b13a888adf9bd1cda4adfdd0e7779425f6bc9823b861e8d5b630",
        [("\tif (selabel_fini(rec, lr, translating))\n\t\treturn NULL;",
          "\tif (selabel_fini(rec, lr, translating)) {\n\t\terrno = EIO;\n\t\treturn NULL;\n\t}")],
    ),
}


def patch(directory: Path) -> None:
    for name, (digest, edits) in PATCHES.items():
        path = directory / "src" / name
        current = path.read_text()
        original = current
        if hashlib.sha256(original.encode()).hexdigest() != digest:
            for before, after in reversed(edits):
                expected = 2 if name == "label.c" else 1
                if original.count(after) != expected:
                    raise RuntimeError(f"untrusted private SELinux patch state: {name}")
                original = original.replace(after, before)
        if hashlib.sha256(original.encode()).hexdigest() != digest:
            raise RuntimeError(f"private SELinux source hash mismatch: {name}")
        modified = original
        for before, after in edits:
            expected = 2 if name == "label.c" else 1
            if modified.count(before) != expected:
                raise RuntimeError(f"private SELinux source shape mismatch: {name}")
            modified = modified.replace(before, after)
        if current not in (original, modified):
            raise RuntimeError(f"unexpected private SELinux modifications: {name}")
        if current != modified:
            path.write_text(modified)
        print(f"private SELinux {name} sha256={hashlib.sha256(modified.encode()).hexdigest()}")


if __name__ == "__main__":
    patch(Path(sys.argv[1]))

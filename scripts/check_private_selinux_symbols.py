"""Verify actual ELF consumers have no dynamic private-backend binding."""
import subprocess
import sys


def check(archive: str, consumers: list[str]) -> None:
    definitions = subprocess.check_output(["nm", "-g", "--defined-only", archive], text=True)
    private = {line.split()[-1] for line in definitions.splitlines()
               if len(line.split()) >= 3 and line.split()[-2].isalpha()}
    if "selabel_lookup_raw" not in private:
        raise RuntimeError("private archive symbol inventory is incomplete")
    for consumer in consumers:
        output = subprocess.check_output(["readelf", "--dyn-syms", "--wide", consumer], text=True)
        exposed = set()
        for line in output.splitlines():
            fields = line.split()
            if len(fields) >= 8 and fields[0].endswith(":"):
                name = fields[7].split("@", 1)[0]
                if name in private:
                    exposed.add(name)
        if exposed:
            raise RuntimeError(f"private SELinux dynamic binding in {consumer}: {sorted(exposed)}")
        print(f"private SELinux ELF boundary verified: {consumer}")


if __name__ == "__main__":
    check(sys.argv[1], sys.argv[2:])

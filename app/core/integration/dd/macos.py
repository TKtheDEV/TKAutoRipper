# app/core/integration/dd/macos.py
from pathlib import Path
from typing import List


def build_iso_dump_cmd(device: str, output_path: Path) -> List[str]:
    """
    Use plain dd, stream progress to STDOUT (so the runner can parse it),
    and fsync writes so partial files are durable on cancel.

    Some macOS optical stacks return EINVAL at end-of-medium. We consider the
    dump successful iff the output size meets the device size from `diskutil`.

    `device` should be a real block device path, e.g. '/dev/rdisk2'.
    """
    sh = rf'''
        DEV="{device}"
        OUT="{output_path}"
        expected=$(diskutil info "$DEV" | sed -n 's/.*(\([0-9]*\) Bytes).*/\1/p' | head -n1)
        rc=0
        dd if="$DEV" of="$OUT" bs=2048 status=progress conv=fsync 2>&1 || rc=$?
        out_size=$(stat -f%z "$OUT" 2>/dev/null || echo 0)
        if [ -n "$expected" ] && [ "$expected" -gt 0 ]; then
            if [ "$out_size" -ge "$expected" ]; then
                if [ "$rc" -ne 0 ]; then
                    echo "[TKAR] dd exited $rc but wrote full size $out_size/$expected bytes – treating as success."
                fi
                exit 0
            fi
            echo "[TKAR] dd wrote $out_size of $expected bytes; failing." >&2
            fail_rc=$rc; [ "$fail_rc" -eq 0 ] && fail_rc=1
            exit "$fail_rc"
        fi
        # If we can't determine expected size, honor dd's exit code.
        exit "$rc"
    '''
    return ["bash", "-lc", sh]

#!/usr/bin/env python3
"""Can this torch run CUDA kernels on this GPU? The ch09 CUDA legs ask before they run.

torch.cuda.is_available() is True on a GPU whose architecture the installed torch build has no kernels for; every
kernel launch then fails with "no kernel image is available for execution on the device", which a check would
otherwise record as a pyharp CUDA failure. The case that matters: torch 2.10.0+cu126 (the report's pin) ships SASS
for sm_50 ... sm_90 and no PTX, so it cannot run on an sm_120 GPU (RTX 50xx); torch 2.10.0+cu128 ships sm_120
(ch09_setup.sh installs it on such a host).

The rule is torch's own (a build runs on a device when it carries SASS of the same major architecture and a minor
version not above the device's, or PTX of an architecture not above it), followed by one tiny kernel launch when a
device is present.

    python3 cuda_capability.py           # prints "ok: ..." (exit 0) or "skip: <reason>" (exit 3)
    CUDA_CAPABILITY_SIMULATE=12.0 python3 cuda_capability.py    # judge as if the device were sm_120 (no launch)
    CUDA_SKIP_REASON=...       # a caller (ch09_run.sh) that already decided to skip, and hid the GPU, passes its reason
"""

import os
import sys

SKIP_EXIT = 3


def _archs(arch_list, prefix):
    out = set()
    for a in arch_list:
        if a.startswith(prefix):
            digits = "".join(ch for ch in a[len(prefix):] if ch.isdigit())
            if digits:
                out.add(int(digits))
    return out


def skip_reason(available, capability, arch_list, device="the GPU", torch_version="torch"):
    """None when this torch build can run kernels on a device of `capability` (major, minor), else the reason."""
    if not available:
        return "no CUDA device"
    major, minor = capability
    sm = 10 * major + minor
    sass, ptx = _archs(arch_list, "sm_"), _archs(arch_list, "compute_")
    if any(s // 10 == major and s % 10 <= minor for s in sass) or any(p <= sm for p in ptx):
        return None
    have = ", ".join(sorted(arch_list, key=lambda a: (a.split("_")[0], int("".join(c for c in a if c.isdigit()) or 0))))
    fix = ("ch09_setup.sh installs torch 2.10.0+cu128, which has sm_120, on such a host" if sm >= 120 else
           "no torch build the setup scripts pin has kernels for it")
    return f"torch {torch_version} has no kernels for {device} (sm_{sm}): it ships {have or 'none'}; {fix}"


def probe():
    """(reason or None, description) for the first visible device, from the installed torch."""
    import torch
    if os.environ.get("CUDA_SKIP_REASON"):  # ch09_run.sh decided already, then hid the GPU
        return os.environ["CUDA_SKIP_REASON"], "decided by the caller"
    sim = os.environ.get("CUDA_CAPABILITY_SIMULATE")
    if sim:
        major, minor = (int(x) for x in sim.split("."))
        name = f"a simulated sm_{major}{minor} device"
        return skip_reason(True, (major, minor), torch.cuda.get_arch_list(), name, torch.__version__), name
    if not torch.cuda.is_available():
        return skip_reason(False, (0, 0), []), "no device"
    cap = torch.cuda.get_device_capability(0)
    name = torch.cuda.get_device_name(0)
    reason = skip_reason(True, cap, torch.cuda.get_arch_list(), name, torch.__version__)
    if reason is None:
        try:
            (torch.ones(4, device="cuda") * 2).sum().item()
        except Exception as e:  # noqa: BLE001 - the message is the reason
            reason = f"a CUDA kernel launch on {name} failed: {str(e).splitlines()[0][:160]}"
    return reason, f"{name} (sm_{cap[0]}{cap[1]})"


def main():
    reason, what = probe()
    if reason is None:
        print(f"ok: {what}")
        return 0
    print(f"skip: {reason}")
    return SKIP_EXIT


if __name__ == "__main__":
    sys.exit(main())

"""uiready.py 의 다중 실행 여부와 순서를 실제 GUI 세션으로 실측한다.

uiready.py 는 인터랙티브 세션에서만 실행되므로 hython 으로는 검증할 수 없다.
이 스크립트는 Houdini 창을 실제로 띄웠다가 자동으로 닫는다 (watchdog 패키지가
hou.exit 을 예약한다). 한 번 실행에 1~2분 걸린다.

    python gui_probe.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from harness import Package, PackageLab, make_gui_watchdog


def main() -> int:
    packages = [
        Package("A"),
        Package("B"),
        Package("C"),
        make_gui_watchdog(),
    ]

    print("Houdini GUI 를 띄웁니다. 창이 자동으로 닫힐 때까지 기다리세요...")
    with PackageLab(packages) as lab:
        result = lab.run_gui()

    on_path = [
        Path(entry).name for entry in result.houdini_path if "zzhmcptest_" in entry
    ]

    print(f"\nreturncode: {result.returncode}")
    print(f"HOUDINI_PATH 상의 테스트 패키지: {on_path}")

    print("\n훅별 실행 순서:")
    for hook in ("pythonrc", "ready", "uiready", "123", "456"):
        order = result.order_of(hook)
        print(f"  {hook:9s} -> {order if order else '(실행 안 됨)'}")

    uiready = [pkg for pkg in result.order_of("uiready") if pkg != "WATCHDOG"]
    print("\n판정:")
    if len(uiready) == 3:
        print(f"  uiready.py 는 모든 패키지에서 실행됨. 순서: {uiready}")
        if uiready == result.order_of("pythonrc"):
            print("  순서가 pythonrc 와 동일 = HOUDINI_PATH 순서를 따름.")
        else:
            print(f"  주의: pythonrc 순서({result.order_of('pythonrc')})와 다름.")
    elif len(uiready) == 1:
        print(f"  uiready.py 는 하나만 실행됨 ({uiready}). 123.py 와 같은 방식.")
    elif not uiready:
        print("  uiready.py 가 전혀 실행되지 않음. GUI 기동 실패 가능성.")
        if result.stderr:
            print(f"\nstderr:\n{result.stderr[:2000]}")
        return 1
    else:
        print(f"  예상 밖의 결과: {uiready}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Print the release metrics of every workspace: python -m ichnos.evaluate (make metrics)."""

from sqlalchemy import select

from ichnos.db.engine import make_engine, make_session_factory
from ichnos.db.models import Workspace
from ichnos.evaluate.metrics import compute_metrics
from ichnos.settings import Settings

VERDICT = {True: "pass", False: "FAIL", None: "no data"}


def main() -> None:
    with make_session_factory(make_engine(Settings()))() as session:
        for workspace in session.scalars(select(Workspace)):
            print(f"\n{workspace.name} ({workspace.repo_owner}/{workspace.repo_name})")
            for metric in compute_metrics(session, workspace):
                if metric.value is None:
                    shown = "n/a"
                elif metric.higher_is_better:
                    shown = f"{metric.value:.0%}"
                else:
                    shown = f"{metric.value:.0f}"
                print(
                    f"  {metric.label:<40} {metric.numerator:>3} of {metric.denominator:<3}"
                    f" {shown:>5}  {VERDICT[metric.passed]}"
                )
                for detail in metric.details[:6]:
                    print(f"      - {detail}")


if __name__ == "__main__":
    main()

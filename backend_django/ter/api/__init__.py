"""TER API controllers."""

from .periods import TERPeriodController
from .rankings import TERRankingController
from .subjects import TERSubjectController

__all__ = [
    "TERPeriodController",
    "TERSubjectController",
    "TERRankingController",
]

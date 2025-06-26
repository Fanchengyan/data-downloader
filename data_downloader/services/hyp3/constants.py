from __future__ import annotations


class ConstantsMeta(type):
    def __contains__(cls, item):
        variables = [
            prop
            for prop in dir(cls)
            if not prop.startswith("_") and not callable(getattr(cls, prop))
        ]
        return item in variables


class BaseConstants(metaclass=ConstantsMeta):
    @classmethod
    def variables(cls) -> list[str]:
        """all available variables"""
        variables = [
            prop
            for prop in dir(cls)
            if not prop.startswith("_") and not callable(getattr(cls, prop))
        ]
        return variables


class JOB_TYPE(BaseConstants):
    AUTORIFT = "AUTORIFT"
    RTC_GAMMA = "RTC_GAMMA"
    INSAR_GAMMA = "INSAR_GAMMA"
    INSAR_ISCE_BURST = "INSAR_ISCE_BURST"


class STATUS_CODE(BaseConstants):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    RUNNING = "RUNNING"
    PENDING = "PENDING"


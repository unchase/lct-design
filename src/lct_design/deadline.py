import time

class BudgetExpired(TimeoutError):
    pass

class Deadline:
    def __init__(self,seconds=300,clock=time.monotonic):
        self.clock=clock;self.end=clock()+seconds
    def remaining(self,cap=None):
        value=self.end-self.clock()
        if value<=0:raise BudgetExpired('Общий бюджет генерации исчерпан')
        return min(value,cap) if cap is not None else value

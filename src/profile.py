import cProfile as cp
import io
import pstats as ps


# Profiler decorator
def profiler(func):
    def inner(*args, **kwargs):
        pr = cp.Profile()
        pr.enable()
        retval = func(*args, **kwargs)
        pr.disable()
        s = io.StringIO()
        sortby = 'cumulative'
        pstat = ps.Stats(pr, stream=s).sort_stats(sortby)
        pstat.print_stats()
        print(s.getvalue())
        return retval
    return inner
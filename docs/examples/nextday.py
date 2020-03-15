#!/usr/bin/env python3

"Show how to define a function with complex params as CLI using calf"

import datetime


def nextday(date: datetime.date):
    print('Next day of %s is %s' % (date, date + datetime.timedelta(1)))


if __name__ == '__main__':
    import calf
    def _dateconv(datestr):
        return datetime.datetime.strptime(datestr, '%d/%m/%Y').date()
    calf.CONVERTERS[datetime.date] = _dateconv
    calf.call(nextday)

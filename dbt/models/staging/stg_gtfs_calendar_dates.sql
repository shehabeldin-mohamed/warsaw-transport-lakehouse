select
    service_id,
    cast(strptime(date, '%Y%m%d') as date) as service_date,
    cast(exception_type as integer) as exception_type
from {{ read_gtfs('calendar_dates.txt') }}

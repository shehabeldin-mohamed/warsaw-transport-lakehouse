-- Fails if deduplication left the same reported position twice.
select vehicle_type, vehicle_number, reported_at_utc, count(*) as n
from {{ ref('stg_vehicle_positions') }}
group by all
having count(*) > 1

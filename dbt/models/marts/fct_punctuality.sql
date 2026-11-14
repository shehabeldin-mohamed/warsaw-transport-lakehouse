with visits as (
    select *
    from {{ ref('int_scheduled_stop_visits') }}
    where not is_first_stop and not is_last_stop
),

positions as (
    select
        vehicle_type,
        vehicle_number,
        line,
        brigade,
        lat,
        lon,
        reported_at_utc
    from {{ ref('stg_vehicle_positions') }}
    where not is_stale and is_in_warsaw_area and brigade is not null
),

candidates as (
    select
        visits.service_date,
        visits.trip_id,
        visits.stop_sequence,
        positions.vehicle_number,
        positions.reported_at_utc as observed_at_utc,
        {{ haversine_m('visits.stop_lat', 'visits.stop_lon', 'positions.lat', 'positions.lon') }} as distance_to_stop_m
    from visits
    inner join positions
        on visits.vehicle_type = positions.vehicle_type
        and visits.line = positions.line
        and visits.brigade = positions.brigade
        and positions.reported_at_utc
        between visits.scheduled_at_utc - to_minutes({{ var('punctuality_max_early_minutes', 10) }})
        and visits.scheduled_at_utc + to_minutes({{ var('punctuality_max_late_minutes', 30) }})
),

closest as (
    select *
    from candidates
    where distance_to_stop_m <= {{ var('punctuality_stop_radius_m', 50) }}
    qualify row_number() over (
        partition by service_date, trip_id, stop_sequence
        order by distance_to_stop_m, observed_at_utc
    ) = 1
)

select
    visits.service_date,
    visits.trip_id,
    visits.vehicle_type,
    visits.line,
    visits.brigade,
    visits.direction_id,
    visits.headsign,
    visits.stop_sequence,
    visits.stop_id,
    visits.stop_name,
    visits.scheduled_at_utc,
    closest.vehicle_number,
    closest.observed_at_utc,
    round(closest.distance_to_stop_m, 1) as distance_to_stop_m,
    epoch(closest.observed_at_utc - visits.scheduled_at_utc) as delay_seconds,
    closest.trip_id is not null as is_observed
from visits
left join closest
    on visits.service_date = closest.service_date
    and visits.trip_id = closest.trip_id
    and visits.stop_sequence = closest.stop_sequence

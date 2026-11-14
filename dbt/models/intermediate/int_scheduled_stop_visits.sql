with observed_minutes as (
    select distinct date_trunc('minute', reported_at_utc) as minute_utc
    from {{ ref('stg_vehicle_positions') }}
    where not is_stale
),

services as (
    select distinct
        calendar.service_id,
        calendar.service_date
    from {{ ref('stg_gtfs_calendar_dates') }} as calendar
    inner join observed_minutes
        on calendar.service_date between cast(observed_minutes.minute_utc as date) - 1
        and cast(observed_minutes.minute_utc as date)
    where calendar.exception_type = 1
),

visits as (
    select
        services.service_date,
        trips.trip_id,
        case
            when routes.route_type in (0, 900) then 2
            when routes.route_type in (3, 700) then 1
        end as vehicle_type,
        routes.line,
        trips.brigade,
        trips.direction_id,
        trips.headsign,
        stop_times.stop_sequence,
        stop_times.stop_sequence = min(stop_times.stop_sequence) over trip as is_first_stop,
        stop_times.stop_sequence = max(stop_times.stop_sequence) over trip as is_last_stop,
        stop_times.stop_id,
        stops.stop_name,
        stops.stop_lat,
        stops.stop_lon,
        timezone(
            'Europe/Warsaw',
            services.service_date + to_seconds(stop_times.departure_seconds)
        ) as scheduled_at_utc
    from services
    inner join {{ ref('stg_gtfs_trips') }} as trips
        on services.service_id = trips.service_id
    inner join {{ ref('stg_gtfs_routes') }} as routes
        on trips.route_id = routes.route_id
    inner join {{ ref('stg_gtfs_stop_times') }} as stop_times
        on trips.trip_id = stop_times.trip_id
    inner join {{ ref('stg_gtfs_stops') }} as stops
        on stop_times.stop_id = stops.stop_id
    window trip as (partition by services.service_date, trips.trip_id)
)

select visits.*
from visits
inner join observed_minutes
    on date_trunc('minute', visits.scheduled_at_utc) = observed_minutes.minute_utc
where visits.vehicle_type is not null

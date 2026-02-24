def score_transit_gap(trip_data: dict, gap_minutes: int):
    """
    calculates a score to rank the bus trip
    trip_data is based on travel_time, wait_time, and destination_hub
    """
    # 1. Base Score
    score = 100
    
    # 2. Hard Constraint: If trip + buffer > gap, it's useless
    total_time_required = trip_data['travel_time'] + trip_data['wait_time'] + 5 # 5m buffer
    if total_time_required > gap_minutes:
        return 0

    # 3. Penalty for Waiting (Efficiency)
    # Students hate standing at stops. -2 points per minute of waiting.
    score -= (trip_data['wait_time'] * 2)

    # 4. Penalty for long travel (Utility)
    # If you spend the whole gap on a bus, you can't study. -1 point per minute.
    score -= trip_data['travel_time']

    # 5. Study Spot Bonus
    # If the bus drops you at a Hub (University Center/Engineering), +20 points.
    if trip_data['is_study_hub']:
        score += 20

    return max(0, score)
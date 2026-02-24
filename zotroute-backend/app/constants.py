# Mapping common UCI building codes to their nearest Anteater Express stop_id
BUILDING_TO_STOP = {
    # North/Social Sciences
    "HIB": "anteater-express:100", "SSH": "anteater-express:100", 
    "SSLH": "anteater-express:100", "SST": "anteater-express:100",
    "ALH": "anteater-express:107", "LLIB": "anteater-express:107",
    
    # Engineering/ICS (East)
    "DBH": "anteater-express:16", "EH": "anteater-express:16",
    "ET": "anteater-express:16", "ICT": "anteater-express:16",
    "MDE": "anteater-express:16", "REC": "anteater-express:16",
    
    # Physical Sciences/MSTB (South)
    "MSTB": "anteater-express:17", "PSLH": "anteater-express:17",
    "RH": "anteater-express:17", "FRH": "anteater-express:17",
    "PSCB": "anteater-express:17",
    
    # BioSci/Arts
    "BS3": "anteater-express:166", "NS1": "anteater-express:166",
    "SH": "anteater-express:166", "CTT": "anteater-express:166"
}

STUDY_HUBS = ["anteater-express:100", "anteater-express:161", "anteater-express:107"]

# Known landmarks mapped to their nearest stop ID.
# "mode" indicates how a student is expected to arrive:
#   - "walk": close enough to walk to from a nearby stop
#   - "bus": requires taking a bus to reach
# When user preferences are implemented, this will be used to filter
# suggestions based on what the user wants to do with their gap.


# THese are just some placeholders!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
LANDMARKS = {
    "anteater-express:11": {
        "name": "University Town Center",
        "description": "Shopping and dining near campus",
        "mode": "walk",
    },
    "octa:7336": {
        "name": "Hong Kong Express",
        "description": "Hong Kong Express, 15452 Beach Blvd, Westminster",
        "mode": "bus",
    },
}


for w in ["$29.83/hour", "$29.83 per hour.", "$31.56 - $33.28", "$37.89 - $47.31/hour","$41.42 to $59.52 per hour.", "$74,618.00 - $107,264.00"]:
    min_val = ""
    max_val = ""
    found_min = False
    found_max = False
    for c in w:
        if c == "$":
            if min_val == "":
                found_min = True
            else:
                found_max = True
        elif c.isdigit() or c == "." or c == ",":
            if found_min:
                min_val += c
            if found_max:
                max_val += c
        else:
            found_min, found_max = False, False
    min_val = min_val.replace(",","")
    max_val = max_val.replace(",","")
    if max_val == "":
        max_val = min_val
    print(w, float(min_val), float(max_val))
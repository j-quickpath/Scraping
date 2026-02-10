
import csv
from datetime import datetime

all_jobs_data = []

def load_csv_data(filename):
    """
    Load data from CSV file into all_jobs_data list.
    """
    
    try:
        with open(filename, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                all_jobs_data.append(row)
        
        print(f"Loaded {len(all_jobs_data)} jobs from {filename}")
        return True
        
    except FileNotFoundError:
        print(f"Error: {filename} not found.")
        return False
    except Exception as e:
        print(f"Error loading CSV: {str(e)}")
        return False

def save_cleaned_csv():
    """
    Save cleaned data to a new CSV file.
    """
    if not all_jobs_data:
        print("No data to save.")
        return
    
    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"cleaned_jobs_{timestamp}.csv"
    
    # Get headers from the first job data (assuming all have same keys)
    if all_jobs_data:
        headers = list(all_jobs_data[0].keys())
    else:
        print("No data to determine headers.")
        return
    
    try:
        # utf-8-sig instead of utf-8 to fix encoding issues
        with open(filename, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=headers)
            
            # Write the header row
            writer.writeheader()
            
            # Write all job data
            for job_data in all_jobs_data:
                writer.writerow(job_data)
        
        print(f"Successfully saved cleaned data to {filename}")
        
    except Exception as e:
        print(f"Error saving CSV file: {str(e)}")

def clean_data(): # original clean data function from scraper.py
    if not all_jobs_data:
        print("No job data to clean.")
        return
    
    print("Cleaning job data...")
    
    # Character replacements mapping
    replacements = {
        '’': "'",  
        '–': '-',
        '•': '-'
    }
    
    cleaned_count = 0
    
    for job_data in all_jobs_data:
        job_data['Min_Wage'] = 0
        job_data["Max_Wage"] = 0
        for field_name, field_value in job_data.items():
            if isinstance(field_value, str) and field_value:
                original_value = field_value
                
                # Apply all character replacements
                for bad_char, good_char in replacements.items():
                    field_value = field_value.replace(bad_char, good_char)
                
                # Update the field if it was changed
                if field_value != original_value:
                    job_data[field_name] = field_value
                    cleaned_count += 1

            # update wages: splitting into min and max
            if field_name == "Wage":
                try:
                    min_val = ""
                    max_val = ""
                    found_min = False
                    found_max = False
                    for c in job_data[field_name]:
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
                    # to allow conversion to float
                    min_val = min_val.replace(",","")
                    max_val = max_val.replace(",","")
                    # no number given - just a description
                    if min_val == "":
                        job_data["Min_Wage"] = job_data['Wage']
                        job_data["Max_Wage"] = job_data['Wage']
                        continue
                    # no range - just one value
                    if max_val == "":
                        max_val = min_val
                    job_data["Min_Wage"] = float(min_val)
                    job_data["Max_Wage"] = float(max_val)
                    
                except ValueError as e:
                    print(f"Error parsing wage '{field_value}': {e}")
                    job_data["Min_Wage"] = job_data['Wage']
                    job_data["Max_Wage"] = job_data['Wage']
    
    print(f"Cleaned {cleaned_count} field(s) with encoding issues.")


# Load data from CSV
if load_csv_data("to_clean.csv"):
    # Clean the data
    clean_data()

    # Save cleaned data
    save_cleaned_csv()

    print("Cleaning process completed!")
else:
    print("No data")

# NOTE: FOR NOW, LET'S KEEP WAGE AS JUST TEXT -- WILL SPLIT INTO INTEGERS LATER (maybe using AI)

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.window import WindowTypes
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
import json
import requests
import time
import re
import csv
from datetime import datetime

driver = webdriver.Chrome()

# NOTE: COMMENT THIS WHEN TESTING
# driver.get("https://jobs.phsa.ca/search-jobs/care%20aid/909/1?glat=43.7968&glon=-79.38212")

# timeout after 10 seconds
wait = WebDriverWait(driver, 10)

# Add this at the top level to store all scraped job data
all_jobs_data = []

def clean_data():
    if not all_jobs_data:
        print("No job data to clean.")
        return
    
    print("Cleaning job data...")
    
    # Character replacements mapping
    replacements = {
        '’': "'",  
        '–': '-'
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

def save_csv():
    """
    Save all scraped job data to a CSV file.
    """
    if not all_jobs_data:
        print("No job data to save.")
        return
    
    # clean data
    clean_data()
    
    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"scraped_jobs_{timestamp}.csv"
    
    # Define CSV headers based on the data returned from scrape_job()
    headers = [
        'Job_URL',
        'Job_Title', 
        'Job_Desc',
        'Qualifications',
        'Skills',
        'Company',
        'Job_Type',
        'Wage',
        'Min_Wage',
        'Max_Wage',
        'Location',
        'Hours_of_Work',
        'Requisition',
        'Date_Posted'
    ]
    
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            # DictWriter ensures order is kept
            writer = csv.DictWriter(csvfile, fieldnames=headers)
            
            # Write the header row
            writer.writeheader()
            
            # Write all job data
            for job_data in all_jobs_data:
                writer.writerow(job_data)
        
        print(f"Successfully saved {len(all_jobs_data)} jobs to {filename}")
        
    except Exception as e:
        print(f"Error saving CSV file: {str(e)}")


# helper for extracting company posting the job
def extract_company(description_elem):
    try:
        # Find all p elements under description_class
        p_elements = description_elem.find_elements(By.TAG_NAME, "p")
        second_p_text = ""

        if len(p_elements) >= 2:
            # Try to get company from second <p>
            second_p_text = p_elements[1].text.strip()
            if second_p_text:
                return second_p_text
        
        # If second <p> doesn't exist or is empty, use the first p
        if len(p_elements) >= 1 or not second_p_text:
            first_p = p_elements[0]
            # Look for spans within the first p
            spans = first_p.find_elements(By.TAG_NAME, "span")
            if spans:
                first_span = spans[0]
                # Get all text nodes that are not within <strong> tags
                company_text = driver.execute_script("""
                    var span = arguments[0];
                    var text = '';
                    for (var i = 0; i < span.childNodes.length; i++) {
                        var node = span.childNodes[i];
                        if (node.nodeType === 3) { // Text node
                            text += node.textContent;
                        } else if (node.nodeType === 1 && node.tagName.toLowerCase() !== 'strong') {
                            // Element node that's not <strong>
                            text += node.textContent;
                        }
                    }
                    return text.trim();
                """, first_span)
                return company_text
        
        return ""
    except Exception as e:
        print(f"Error extracting company: {str(e)}")
        return ""

# for values with headings:
def extract_job_details(description_elem):
    """
    Extract Job Type, Wage, Location, Hours of Work, and Requisition from the description.
    Simplified approach: find keywords and extract text after </strong>
    """
    try:
        # Get all text content from the description element
        full_text = description_elem.get_attribute('innerHTML')
        
        # Dictionary to store extracted values
        job_details = {
            'Job_Type': '',
            'Wage': '',
            'Location': '',
            'Hours_of_Work': '',
            'Requisition': ''
        }
        
        # Simple approach: find the keyword, then extract text after </strong>
        def extract_after_keyword(keyword, stop_words=None):
            # Look for the keyword followed by </strong> and capture what comes after
            pattern = rf'{keyword}[^<]*</strong>\s*([^<]*(?:<(?!strong)[^>]*>[^<]*</[^>]*>)*[^<]*?)(?=<strong|</span|</p|<br|$)'
            
            match = re.search(pattern, full_text, re.IGNORECASE | re.DOTALL)
            if match:
                value = match.group(1).strip()
                # Remove HTML tags and decode entities
                value = re.sub(r'<[^>]+>', '', value)
                value = re.sub(r'&amp;', '&', value)
                value = re.sub(r'&nbsp;', ' ', value)
                value = re.sub(r'\s+', ' ', value).strip()
                
                # Remove common trailing artifacts
                value = re.sub(r'^\s*[-–—]\s*', '', value)
                value = re.sub(r'\s*[-–—]\s*$', '', value)
                
                return value
            return ""
        
        # Extract each field
        job_details['Job_Type'] = extract_after_keyword("Job Type")
        job_details['Wage'] = extract_after_keyword("Wage")
        if job_details['Wage'] == "":
            job_details['Wage'] = extract_after_keyword("Salary Range")
        job_details['Location'] = extract_after_keyword("Location") 
        job_details['Hours_of_Work'] = extract_after_keyword("Hours of Work")
        job_details['Requisition'] = extract_after_keyword("Requisition")
        
        # Debug output
        for field, value in job_details.items():
            if value:
                print(f"DEBUG - Found {field}: '{value}'")
            else:
                print(f"DEBUG - No match for {field}")
        
        return job_details
        
    except Exception as e:
        print(f"Error extracting job details: {str(e)}")
        return {
            'Job_Type': '',
            'Wage': '',
            'Location': '',
            'Hours_of_Work': '',
            'Requisition': ''
        }

def scrape_job():
    try:
        title = driver.find_element(By.CLASS_NAME, "job-title").text
        description_class = "ats-description"
    except NoSuchElementException:
        # one of the pages is diff: https://jobs.phsa.ca/job/surrey/forensic-services-officer-surrey-mental-health-unit-surrey-bc-correctional-health-services/909/83358543648
        title = driver.find_element(By.CLASS_NAME, "ajd_job-details__title").text
        description_class = "ats-description.ajd_job-details__ats-description"
    
    description_elem = driver.find_element(By.CLASS_NAME, description_class)

    # Helper function to extract bullet points after a heading
    def extract_list_after_heading(heading_text):
        try:
            # Find all p elements within the description
            p_elements = description_elem.find_elements(By.TAG_NAME, "p")
            
            # Look for the p element containing the heading text
            for p in p_elements:
                if heading_text.lower() in p.text.lower():
                    # Found the heading, now look for the next ul element
                    # Get the first ul after the p element
                    elem = driver.execute_script("""
                        var element = arguments[0];
                        var next = element.nextElementSibling;
                        while (next) {
                            if (next.tagName.toLowerCase() === 'ul') {
                                return next;
                            }
                            next = next.nextElementSibling;
                        }
                        return null;
                    """, p) # arguments[0] refers to p
                    # the above is equivalent to copy pasting into console after selecting the p element with mouse
                    # var element = $0;  // $0 is the currently selected element
                    # var next = element.nextElementSibling;
                    # while (next) {
                    #     if (next.tagName.toLowerCase() === 'ul') {
                    #         console.log("FOUND UL:", next);
                    #         break;  // Add break to stop after finding
                    #     }
                    #     console.log("Checking:", next.tagName, next);
                    #     next = next.nextElementSibling;
                    # }
                    # console.log("Done searching");

                    if not elem: # no ul found
                        return ""
                    
                    # Extract text from all li elements within ul
                    li_elements = elem.find_elements(By.TAG_NAME, "li")
                    bullet_points = [li.text.strip() for li in li_elements if li.text.strip()]
                    return " - ".join(bullet_points)
            
            return "" # header was not found
        except Exception as e:
            print(f"Error extracting {heading_text}: {str(e)}")
            return ""
    
    # Extract the three sections 
    what_you_do = extract_list_after_heading("What you’ll do")
    if what_you_do == "":
        what_you_do = extract_list_after_heading("What you'll do")
    qualifications = extract_list_after_heading("Qualifications")
    # if not found, then use "You have:"
    skills_knowledge = extract_list_after_heading("Skills & Knowledge")
    if skills_knowledge == "":
        skills_knowledge = extract_list_after_heading("You have:")
    company = extract_company(description_elem)

    # to get wages, employee type, etc
    job_details = extract_job_details(description_elem)

    # extract date posted
    date_posted = ""
    try:
        # Find the script tag with type="application/ld+json"
        script_tag = driver.find_element(By.CSS_SELECTOR, 'script[type="application/ld+json"]')
        script_content = script_tag.get_attribute('innerHTML')
        
        # Parse the JSON content
        import json
        job_data = json.loads(script_content)
        
        # Extract datePosted
        date_posted = job_data.get('datePosted', '')
        print(f"DEBUG - Found datePosted: '{date_posted}'")
        
    except NoSuchElementException:
        print("DEBUG - No JSON-LD script tag found")
    except json.JSONDecodeError:
        print("DEBUG - Could not parse JSON content")
    except Exception as e:
        print(f"DEBUG - Error extracting datePosted: {str(e)}")

    print(f"Title: {title}")
    # print(f"What you'll do: {what_you_do}")
    # print(f"Qualifications: {qualifications}")
    # print(f"Skills & Knowledge: {skills_knowledge}")
    print(f"Company: {company}")
    print(f"Job Type: {job_details['Job_Type']}")
    print(f"Wage: {job_details['Wage']}")
    print(f"Location: {job_details['Location']}")
    print(f"Hours of Work: {job_details['Hours_of_Work']}")
    print(f"Requisition: {job_details['Requisition']}")
    print(f"Date Posted: {date_posted}") 
    print("-" * 50)
    
    # Return the data for CSV saving
    return {
        'Job_Title': title,
        'Job_Desc': what_you_do,
        'Qualifications': qualifications,
        'Skills': skills_knowledge,
        'Company': company,
        'Job_Type': job_details['Job_Type'],
        'Wage': job_details['Wage'],
        'Location': job_details['Location'],
        'Hours_of_Work': job_details['Hours_of_Work'],
        'Requisition': job_details['Requisition'],
        'Date_Posted': date_posted
    }

# test the normal one
# driver.get("https://jobs.phsa.ca/job/coquitlam/health-care-worker-float-pool-forensic-psychiatric-hospital-coquitlam-bc/909/88116687056")

# test the weird one
# driver.get("https://jobs.phsa.ca/job/surrey/forensic-services-officer-surrey-mental-health-unit-surrey-bc-correctional-health-services/909/83358543648")
# test You have: instead of skills AND test the weird company title format
# driver.get("https://jobs.phsa.ca/job/kelowna/radiation-therapist-radiation-oncology-bc-cancer-kelowna/909/87769629840")

# for testing
driver.get("https://jobs.phsa.ca/job/vancouver/provincial-professional-practice-leader-medical-radiation-technologists-bc-cancer-vancouver/909/87319312336")
print(scrape_job())

def scrape_jobs_on_page():
    try:
        # Store the original window handle (the job listings page)
        original_window = driver.current_window_handle

        # list of all jobs on this page (under the specified id, take all elements with the tag <li>)
        job_items = driver.find_element(By.ID, "search-results-list").find_elements(By.TAG_NAME, "li")
        print(f"Found {len(job_items)} job listings on this page")
        
        # all jobs on this page (url)
        job_urls = []
        for job_item in job_items:
            try:
                # Find the <a> tag within each <li>
                job_link = job_item.find_element(By.TAG_NAME, "a")
                job_url = job_link.get_attribute("href")
                if job_url:
                    job_urls.append(job_url)
            except NoSuchElementException:
                print("No link found in job item, skipping...")
                continue
                
        print(f"Found {len(job_urls)} valid job URLs")
        
        # Navigate to each job page
        for i, job_url in enumerate(job_urls, 1):
            print(f"Processing job {i}/{len(job_urls)}: {job_url}")
            
            # Open a new blank tab and switch to it
            driver.switch_to.new_window(WindowTypes.TAB) 

            # Navigate to job detail page
            driver.get(job_url)
            
            # Wait for job page to load (ie. body tags loaded)
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            
            # Call function to scrape individual job details
            job_data = scrape_job()
            
            # Add the job URL to the data
            if job_data:
                job_data['Job_URL'] = job_url
                all_jobs_data.append(job_data)
                print(f"Successfully scraped job {i}")
            else:
                print(f"Failed to scrape job {i}")

            # close the current job tab
            driver.close()

            # Switch back to the original tab (job listings page)
            driver.switch_to.window(original_window)


    except Exception as e:
        print(str(e))

def go_next_page():
    """
    Navigate to the next page by clicking the 'Next' button.
    Returns True if successfully navigated to next page, False if no more pages.
    """
    try:
        
        # Get current page number from pagination input
        pagination_input = driver.find_element(By.ID, "pagination-current-bottom")
        current_page = int(pagination_input.get_attribute("value"))
        expected_next_page = current_page + 1
        
        # Look for the next button with class "next" that is NOT disabled
        next_button = driver.find_element(By.CSS_SELECTOR, "a.next:not(.disabled)")
        
        if next_button:
            print(f"Currently on page {current_page}, navigating to page {expected_next_page}")
            
            # Click the next button
            driver.execute_script("arguments[0].click();", next_button)
            
            # Wait for the pagination input value to change to the next page
            # need to get the pagination fresh each time because the elements get recreated
            # so must find elements again when using wait conditions

            # Handle stale elements during DOM updates
            def check_page_updated(driver):
                try:
                    pagination_element = driver.find_element(By.ID, "pagination-current-bottom")
                    current_value = int(pagination_element.get_attribute("value"))
                    return current_value == expected_next_page
                except (StaleElementReferenceException, NoSuchElementException):
                    # pagination element is stale or missing during update - keep waiting (instead of just erroring)
                    return False
                except ValueError:
                    # Invalid value during transition - keep waiting  
                    return False
                
            # wait until true
            wait.until(check_page_updated)
            
            print(f"Successfully navigated to page {expected_next_page}")
            return expected_next_page
        
        return -1 # no next button
            
    except NoSuchElementException:
        print("No next button found or next button is disabled. Reached last page.")
        return -1
    except TimeoutException:
        print("Timeout waiting for page to load after clicking next.")
        return -1
    except Exception as e:
        print(f"Error navigating to next page: {str(e)}")
        return -1

def scrape():
    """
    Main loop that scrapes all pages until there are no more pages.
    """
    page_count = 1
    
    print(f"Starting scraping on page {page_count}")
    
    try:
        while True:
            print(f"Scraping page {page_count}...")
            
            # Scrape jobs on current page (to be implemented)
            scrape_jobs_on_page()
            
            # Try to go to next page
            page = go_next_page()
            if page == -1: # STOP EARLY FOR TESTING: or page == 4
                print("No more pages to scrape. Scraping complete!")
                break
            else:
                page_count = page
        
        print(f"Finished scraping {page_count} pages total.")
        print(f"Total jobs scraped: {len(all_jobs_data)}")
        save_csv()
    except KeyboardInterrupt:
        print("\nScraping interrupted by user. Saving data collected so far...")
        save_csv()
    except Exception as e:
        print(f"Error in main scraping loop: {str(e)}")
        print("Saving data collected so far...")
        save_csv()    

# NOTE: comment when testing
# START
# scrape()

driver.quit()

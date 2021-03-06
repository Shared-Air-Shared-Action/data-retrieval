# This file processes a JSON file to return a list of needed values for Purple Air devices

import json, csv, urllib, sys, os, StringIO, psycopg2
from datetime import datetime, timedelta
import keys

# Open the log file
log = open("/data/sasa_airquality/purpleair/logs/purpleair.log", "a+")

# Create a function for logging/displaying output
def debugMessage(message):
    print(message)
    log.write(message + "\n")
    log.flush()
    os.fsync(log.fileno())

debugMessage("[" + str(datetime.now()) + "] Starting purpleair tool.")

# Connect to the database
try:
    dbConnection = psycopg2.connect(host=keys.hostname, user=keys.username, password=keys.password, dbname=keys.database)
    dbConnection.autocommit = True
    dbCursor = dbConnection.cursor()

except (KeyboardInterrupt, SystemExit):
    debugMessage("[" + str(datetime.now()) + "] Received keyboard interrupt or other system exit signal. Quitting.")
    sys.exit(-1)
except:
    debugMessage("[" + str(datetime.now()) + "] Error connecting to database...");
    sys.exit(-1000)

# Set the URL of the JSON file
JSONurl = 'https://map.purpleair.org/json?inc=246035%7C246037%7C246039%7C246041%7C246044%7C246046%7C246049%7C246051%7C246058%7C246060%7C246063%7C246065%7C246070%7C246072%7C246087%7C246089%7C246094%7C246096%7C246114%7C246116'

# Set the initial date
initialDate = datetime.strptime("2018-05-25","%Y-%m-%d")

# Get the current date
currentDate = datetime.today()

# Set the amount of time to change with each iteration
delta = timedelta(days=1)

# Get the JSON from the URL
JSONresponse = urllib.urlopen(JSONurl).read()

# Their API is encoded in iso-8859-1. We must convert this to utf8 for JSON to parse.
decoded_response = JSONresponse.decode('iso-8859-1').encode('utf8')

# Parse the JSON
JSONdata = json.loads(decoded_response)

# For each date since the initial date
d = initialDate
# Check if the date has run before
dbCursor.execute("SELECT date FROM purpleairdone group by date")

allDates = {}

# store already fetched dates to dictionary
for record in dbCursor:
    allDates[record[0].strftime("%Y-%m-%d")] = 1

print allDates

while d < currentDate:

    dString = d.strftime("%Y-%m-%d")

    # This skips the current loop if the date has run before
    if (dString in allDates):
        debugMessage("[" + str(datetime.now()) + "] Skipping date '" + dString + "' as it has run before.")
        d += delta
        continue

    debugMessage("[" + str(datetime.now()) + "] Running for date '" + dString + "'")

    # For each "result" in the JSON
    for result in JSONdata['results']:
        # First, check that it has a label, otherwise it might fail here
        if (result['Label']):
            # Clean up the label and make uppercase
            fixed_label = result['Label'].upper().replace(" ","").replace("-","_");
            # If the label starts with SASA
            if (fixed_label).startswith("SASA"):

                debugMessage("[" + str(datetime.now()) + "] Requesting data for '" + fixed_label + "' during the date '" + dString + "'")

                # Get the API endpoint ID and key
                thingspeak_id = result['THINGSPEAK_PRIMARY_ID']
                thingspeak_apikey = result['THINGSPEAK_PRIMARY_ID_READ_KEY']

                # Reset community
                community = ''

                # If size is correct to contain a community
                if (len(fixed_label) >= 11):
                    # Get the community from the 3rd spot between _
                    community = fixed_label.split("_")[2]

                    # Make sure it is only two characters
                    community = community[:2]

                # The day to look at (current date in loop)
                start_date = d

                # The next day (data is not inclusive, go up to the current day)
                end_date = d + delta

                try:
                    CSVurl = "https://thingspeak.com/channels/" + thingspeak_id + "/feed.csv?api_key=" + thingspeak_apikey + "&offset=0&average=&round=2&start=" + start_date.strftime("%Y-%m-%d") + "&end=" + end_date.strftime("%Y-%m-%d")

                    CSVresponse = urllib.urlopen(CSVurl).read()
                    CSVdata = csv.reader(StringIO.StringIO(CSVresponse), delimiter=',')

                except (KeyboardInterrupt, SystemExit):
                    debugMessage("[" + str(datetime.now()) + "] Received keyboard interrupt or other system exit signal. Quitting.")
                    sys.exit(-1)
                except:
                    debugMessage("[" + str(datetime.now()) + "] WARNING: Error downloading or parsing CSV for '" + fixed_label + "' during the date (" + d.strftime("%Y-%m-%d") + "). Skipping.")
                    continue

                # Skip the header by using this variable
                checkedHeader = False

                # For each row in the CSV
                for row in CSVdata:
                    if (checkedHeader is True) and (row):

                        # Psycopg2 throws an error on empty strings in non string fields, so make NULL instead
                        if (not row[0]):
                            row[0] = None
                        if (not row[1]):
                            row[1] = None
                        if (not row[2]):
                            row[2] = None
                        if (not row[3]):
                            row[3] = None
                        if (not row[4]):
                            row[4] = None
                        if (not row[5]):
                            row[5] = None
                        if (not row[6]):
                            row[6] = None
                        if (not row[7]):
                            row[7] = None
                        if (not row[8]):
                            row[8] = None
                        if (not row[9]):
                            row[9] = None

                        # This should be all the rows past the header, so enter them into database
                        try:
                            dbCursor.execute("INSERT INTO purpleairprimary (created_at, entry_id, pm1_cf_atm_ugm3, pm25_cf_atm_ugm3, pm10_cf_atm_ugm3, uptimeminutes, rssi_dbm, temperature_f, humidity_percent, pm25_cf_1_ugm3, device_name, community) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",(row[0],row[1],row[2],row[3],row[4],row[5],row[6],row[7],row[8],row[9], fixed_label, community))
                        except (KeyboardInterrupt, SystemExit):
                            debugMessage("[" + str(datetime.now()) + "] Received keyboard interrupt or other system exit signal. Quitting.")
                            sys.exit(-1)
                        except psycopg2.Error as e:
                            # No need to log duplicity errors
                            if ("23505" not in e.pgcode):
                                debugMessage("[" + str(datetime.now()) + "] An error occurred entering data into database. Details:\n" + e.pgerror)
                                sys.exit(-1)

                    # Skip the header
                    else:
                        checkedHeader = True

    # Log that this day has completed
    dbCursor.execute("INSERT INTO purpleairdone(date) VALUES (%s)", (dString,))

    # Go to next day
    d += delta

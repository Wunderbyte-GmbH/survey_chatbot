import requests
import csv
import io


class AddressDownloader:
    def __init__(self):
        self.addresses = []
        self.download_data()

    @staticmethod
    def build_url_for_district(district_number):
        district_string = str(district_number).zfill(2)  # Convert to string and pad leading zero if necessary
        url = (f"https://data.wien.gv.at/daten/geo?service=WFS&request=GetFeature&version=1.1.0&typeName=ogdwien"
               f":ADRESSENOGD&srsName=EPSG:4326&outputFormat=csv&&propertyname=NAME,PLZ,"
               f"GEB_BEZIRK&cql_filter=GEB_BEZIRK='{district_string}'")
        return url

    def download_data(self):
        # Iterate from '01' to '23'
        for district_number in range(1, 24):  # 24 Districts of Vienna
            url = self.build_url_for_district(district_number)
            # Download the dataset
            response = requests.get(url)
            if response.status_code == 200:
                response.encoding = 'utf-8'
                # Parse CSV data
                data = response.text
                csv_reader = csv.reader(io.StringIO(data))
                next(csv_reader)  # Skip header row
                for row in csv_reader:
                    if len(row) > 1:  # Check that row has enough content to prevent IndexErrors
                        self.addresses.append(f'{row[2]}, {row[4]}')
            else:
                print(f'Error: Could not download the data for district {district_number}')

    def get_addresses(self):
        """
        This method returns the addresses that have been downloaded.

        :return: List of addresses
        """
        return self.addresses

    def print_addresses(self):
        for address in self.addresses:
            print(address)

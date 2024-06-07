import logging
from urllib.parse import urlencode
import requests
import csv
import io


class AddressDownloader:
    BASE_URL = "https://data.wien.gv.at/daten/geo"  # Base URL for data download
    SERVICE_DETAIL = {  # Configuration for the service details
        "service": "WFS",
        "request": "GetFeature",
        "version": "1.1.0",
        "typeName": "ogdwien:ADRESSENOGD",
        "srsName": "EPSG:4326",
        "outputFormat": "csv",
        "propertyname": "NAME,PLZ,GEB_BEZIRK"
    }

    def __init__(self):
        """
        Initializes the AddressDownloader instance, setting up an empty list for storing addresses
        and calls the method to download data.
        """
        self.addresses = []  # List to store all downloaded addresses
        self.download_data()  # Initiating the data download on object creation

    @staticmethod
    def __get_district_string(district_number):
        """
        Converts district number into a string and prepends a leading zero if necessary.

        :param district_number: District number as integer
        :return: District number as a 2-digit string
        """
        return str(district_number).zfill(2)

    @staticmethod
    def __build_url_for_district(district_number):
        """
        Builds a URL to fetch data for a specific district based on district_number.

        :param district_number: District number as integer
        :return: Formatted URL as a string
        """
        district_string = str(district_number).zfill(2)  # Convert to string and pad leading zero if necessary
        query_params = {**AddressDownloader.SERVICE_DETAIL}
        query_params.update({"cql_filter": f"GEB_BEZIRK='{district_string}'"})
        url = f"{AddressDownloader.BASE_URL}?{urlencode(query_params)}"
        return url

    @staticmethod
    def __get_data_from_url(url, district_number):
        """
        Sends a GET request to the specified URL and returns the fetched data.
        Logs an error message if unable to download data for a district.

        :param url: URL to fetch data from
        :param district_number: District number for which to fetch data
        :return: fetched data as a string if successful, None otherwise
        """
        response = requests.get(url)
        if response.status_code == 200:
            response.encoding = 'utf-8'
            return response.text
        else:
            logging.error(f'Error: Could not download the data for district {district_number}')
            return None

    def __parse_csv_data(self, data):
        """
        Parses comma-separated tabular data.
        Expects data to have a header row which is omitted during the parse.
        Appends formatted address strings to self.addresses.

        :param data: Input CSV data as a string
        """
        csv_reader = csv.reader(io.StringIO(data))
        next(csv_reader)  # Skip header row
        for row in csv_reader:
            if len(row) > 1:  # Check that row has enough content to prevent IndexErrors
                self.addresses.append(f'{row[2]}, {row[4]}')

    def download_data(self):
        """
        Iterates through all districts (1 to 23) to download, parse and store addresses data.
        """
        # Iterate from '01' to '23'
        for district_number in range(1, 24):  # 24 Districts of Vienna
            url = self.__build_url_for_district(self.__get_district_string(district_number))
            response = self.__get_data_from_url(url, district_number)
            response and self.__parse_csv_data(response)

    def get_addresses(self):
        """
        Returns the addresses that have been downloaded.

        :return: List of addresses
        """
        return self.addresses

    def print_addresses(self):
        """
        Prints all addresses to the standard output (usually, the console).
        """
        for address in self.addresses:
            print(address)

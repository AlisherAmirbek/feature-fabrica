import unittest

import numpy as np

from feature_fabrica.transform import (DateTimeAdd, DateTimeDifference,
                                       DateTimeExtract, DateTimeSubtract)


class TestDateTimeTransform(unittest.TestCase):

    def test_datetime_difference_valid(self):
        # Testing with valid initial datetime and data
        initial_datetime = '2023-01-01'
        data = np.array(['2023-01-05', '2023-01-10'], dtype=np.datetime64)
        transformation = DateTimeDifference(initial_datetime=initial_datetime, compute_unit='D')

        result = transformation.execute(data)

        expected = np.array([4, 9], dtype='timedelta64[D]')
        np.testing.assert_array_equal(result, expected)

        # Testing with valid end datetime and data
        end_datetime = '2023-01-10'
        data = np.array(['2023-01-05', '2023-01-06'], dtype=np.datetime64)
        transformation = DateTimeDifference(end_datetime=end_datetime, compute_unit='D')

        result = transformation.execute(data)

        expected = np.array([5, 4], dtype='timedelta64[D]')
        np.testing.assert_array_equal(result, expected)

        # Both initial_datetime and end_datetime should raise ValueError
        with self.assertRaises(ValueError) as context:
            DateTimeDifference(initial_datetime='2023-01-01', end_datetime='2023-01-05')
        self.assertIn("Only one of 'initial_datetime' or 'end_datetime' should be set!", str(context.exception))

        # Invalid compute_unit should raise ValueError
        with self.assertRaises(ValueError) as context:
            DateTimeDifference(initial_datetime='2023-01-01', compute_unit='invalid')
        self.assertIn("compute_unit= invalid is not a valid code!", str(context.exception))

        # Testing with conversion to a specific datetime format
        initial_datetime = '2023-01-01'
        data = np.array(['2023-01-05', '2023-01-10'], dtype=np.datetime64)
        transformation = DateTimeDifference(initial_datetime=initial_datetime, compute_unit='s')

        result = transformation.execute(data)

        expected = np.array([345600, 777600])
        np.testing.assert_array_equal(result, expected)


    # DateTimeAdd Tests
    def test_datetime_add_days(self):
        data = np.array(['2024-09-10', '2024-09-12'], dtype='datetime64[D]')
        transform = DateTimeAdd(time_delta=2, compute_unit='D')
        result = transform.with_data(data)
        expected = np.array(['2024-09-12', '2024-09-14'], dtype='datetime64[D]')
        np.testing.assert_array_equal(result, expected)

    def test_datetime_add_hours(self):
        data = np.array(['2024-09-10T12', '2024-09-12T06'], dtype='datetime64[h]')
        transform = DateTimeAdd(time_delta=5, compute_unit='h')
        result = transform.with_data(data)
        expected = np.array(['2024-09-10T17', '2024-09-12T11'], dtype='datetime64[h]')
        np.testing.assert_array_equal(result, expected)


    # DateTimeSubtract Tests
    def test_datetime_subtract_days(self):
        data = np.array(['2024-09-10', '2024-09-12'], dtype='datetime64[D]')
        transform = DateTimeSubtract(time_delta=2, compute_unit='D')
        result = transform.with_data(data)
        expected = np.array(['2024-09-08', '2024-09-10'], dtype='datetime64[D]')
        np.testing.assert_array_equal(result, expected)

    def test_datetime_subtract_hours(self):
        data = np.array(['2024-09-10T12', '2024-09-12T06'], dtype='datetime64[h]')
        transform = DateTimeSubtract(time_delta=5, compute_unit='h')
        result = transform.with_data(data)
        expected = np.array(['2024-09-10T07', '2024-09-12T01'], dtype='datetime64[h]')
        np.testing.assert_array_equal(result, expected)


    # DateTimeExtract Tests
    def test_datetime_extract_year(self):
        data = np.array(['2024-09-10', '2023-05-15'], dtype='datetime64[D]')
        transform = DateTimeExtract(component='Y')
        result = transform.execute(data)
        expected = np.array([2024, 2023])
        np.testing.assert_array_equal(result, expected)

    def test_datetime_extract_month(self):
        data = np.array(['2024-09-10', '2023-05-15'], dtype='datetime64[D]')
        transform = DateTimeExtract(component='M')
        result = transform.execute(data)
        expected = np.array([9, 5])
        np.testing.assert_array_equal(result, expected)

    def test_datetime_extract_day(self):
        data = np.array(['2024-09-10', '2023-05-15'], dtype='datetime64[D]')
        transform = DateTimeExtract(component='D')
        result = transform.execute(data)
        expected = np.array([10, 15])
        np.testing.assert_array_equal(result, expected)


    def test_datetime_extract_hour(self):
        data = np.array(['2024-09-10 12:30:45', '2023-05-15 13:20:15'], dtype='datetime64[s]')
        transform = DateTimeExtract(component='h')
        result = transform.execute(data)
        expected = np.array([12, 13])
        np.testing.assert_array_equal(result, expected)


    def test_datetime_extract_minute(self):
        data = np.array(['2024-09-10 12:30:45', '2023-05-15 13:20:15'], dtype='datetime64[s]')
        transform = DateTimeExtract(component='m')
        result = transform.execute(data)
        expected = np.array([30, 20])
        np.testing.assert_array_equal(result, expected)


    def test_datetime_extract_second(self):
        data = np.array(['2024-09-10 12:30:45', '2023-05-15 13:20:15'], dtype='datetime64[s]')
        transform = DateTimeExtract(component='s')
        result = transform.execute(data)
        expected = np.array([45, 15])
        np.testing.assert_array_equal(result, expected)

    def test_datetime_extract_invalid_component(self):
        with self.assertRaises(ValueError):
            DateTimeExtract(component='invalid_component')


if __name__ == '__main__':
    unittest.main()

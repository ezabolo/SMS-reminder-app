import boto3
import os
from dotenv import load_dotenv

load_dotenv()

class SMSService:
    def __init__(self):
        self.client = boto3.client(
            'sns',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_REGION', 'us-east-1')
        )

    def send_sms(self, phone_number, message):
        try:
            response = self.client.publish(
                PhoneNumber=phone_number,
                Message=message,
                MessageAttributes={
                    'SMSType': {
                        'DataType': 'String',
                        'StringValue': 'Transactional'
                    }
                }
            )
            return True, response['MessageId']
        except Exception as e:
            return False, str(e)

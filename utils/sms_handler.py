import boto3
import os
from botocore.exceptions import ClientError
from datetime import datetime

class SMSHandler:
    def __init__(self):
        self.sns_client = boto3.client(
            'sns',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_REGION', 'us-east-1')
        )

    def send_sms(self, phone_number, message):
        try:
            response = self.sns_client.publish(
                PhoneNumber=phone_number,
                Message=message,
                MessageAttributes={
                    'AWS.SNS.SMS.SMSType': {
                        'DataType': 'String',
                        'StringValue': 'Transactional'
                    }
                }
            )
            return {
                'success': True,
                'message_id': response['MessageId']
            }
        except ClientError as e:
            return {
                'success': False,
                'error': str(e)
            }

    def format_appointment_message(self, patient_name, appointment_time, message):
        """Format a standard appointment reminder message"""
        dt = datetime.fromisoformat(appointment_time.replace('Z', '+00:00'))
        formatted_time = dt.strftime('%B %d, %Y at %I:%M %p')
        
        return f"Hello {patient_name},\n\nThis is a reminder for your appointment on {formatted_time}.\n\nDetails: {message}\n\nBest regards,\nArtistic Family Dentistry"

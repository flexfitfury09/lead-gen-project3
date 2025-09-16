"""
AI Email Generator - Advanced email content generation
"""

import random
import os
from typing import Dict, List, Any
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

class AIEmailGenerator:
    def __init__(self):
        self.email_templates = {
            'professional': {
                'greetings': [
                    "Dear {name}",
                    "Hello {name}",
                    "Hi {name}",
                    "Good day {name}"
                ],
                'intros': [
                    "I hope this email finds you well.",
                    "I hope you're having a great day.",
                    "I trust this message reaches you in good health.",
                    "I hope everything is going well at {company}."
                ],
                'bodies': [
                    "I wanted to reach out regarding an exciting opportunity that I believe would be of great interest to {company}. Our innovative solution has helped numerous companies in your industry achieve significant growth and efficiency improvements.",
                    "I came across {company} and was impressed by your recent achievements. I have an opportunity that could help you take your business to the next level.",
                    "I'm reaching out because I believe our solution could provide significant value to {company}. We've helped similar companies achieve remarkable results.",
                    "I wanted to share an exclusive opportunity that I think would be perfect for {company}. Our solution has been proven to deliver measurable results."
                ],
                'value_props': [
                    "Our solution has helped companies achieve up to 40% improvement in efficiency.",
                    "We've seen an average ROI of 300% within the first year.",
                    "Our clients typically see a 50% reduction in operational costs.",
                    "We've helped companies increase revenue by an average of 25%."
                ],
                'ctas': [
                    "I would appreciate the opportunity to schedule a brief 15-minute call to discuss how this could benefit {company}.",
                    "Would you be interested in a quick conversation to explore this opportunity?",
                    "I'd love to show you how this could work for {company}. Are you available for a brief call?",
                    "Could we schedule a short meeting to discuss this further?"
                ],
                'closings': [
                    "Best regards",
                    "Warm regards",
                    "Sincerely",
                    "Thank you for your time"
                ]
            },
            'casual': {
                'greetings': [
                    "Hi {name}",
                    "Hey {name}",
                    "Hello {name}",
                    "Hi there {name}"
                ],
                'intros': [
                    "Hope you're doing well!",
                    "How's it going?",
                    "Hope everything's great at {company}!",
                    "Hope you're having a good day!"
                ],
                'bodies': [
                    "I came across {company} and was really impressed by what you're doing. I thought you might be interested in something that could help take your business to the next level.",
                    "I've been following {company} and I'm really excited about what you're building. I have something that might be perfect for you.",
                    "I stumbled upon {company} and was blown away by your work. I think I have something that could be really valuable for you.",
                    "I've been keeping an eye on {company} and I'm really impressed. I have an opportunity that I think you'd find interesting."
                ],
                'value_props': [
                    "It's pretty cool stuff - we've helped companies like yours save tons of time and money.",
                    "The results are pretty amazing - our clients typically see huge improvements within the first month.",
                    "It's really impressive what we've been able to help companies achieve.",
                    "The feedback has been incredible - companies are seeing massive improvements."
                ],
                'ctas': [
                    "Want to grab a virtual coffee and chat about it?",
                    "Got 10 minutes for a quick call? I'd love to show you what we can do.",
                    "Want to hop on a quick call to see how this could work for you?",
                    "Interested in a brief demo? I think you'll love what you see."
                ],
                'closings': [
                    "Cheers",
                    "Talk soon",
                    "Looking forward to hearing from you",
                    "Thanks!"
                ]
            },
            'urgent': {
                'greetings': [
                    "Dear {name}",
                    "Hello {name}",
                    "Hi {name}"
                ],
                'intros': [
                    "I'm reaching out with an urgent opportunity that requires immediate attention.",
                    "I need to bring something important to your attention.",
                    "This is time-sensitive and I wanted to reach out immediately.",
                    "I have an urgent matter that I believe is critical for {company}."
                ],
                'bodies': [
                    "This exclusive opportunity is only available for a limited time and could significantly impact {company}'s growth. Our solution has helped companies achieve 50% faster results compared to traditional methods.",
                    "This time-sensitive opportunity could transform {company}'s operations. Don't miss out on this chance to gain a competitive advantage.",
                    "This limited-time offer could revolutionize how {company} operates. Time is of the essence and immediate action is required.",
                    "This urgent opportunity could provide {company} with a significant competitive edge. The window for action is closing quickly."
                ],
                'value_props': [
                    "This offer expires in 48 hours and won't be available again.",
                    "Limited spots available - first come, first served.",
                    "This exclusive opportunity is only available to select companies.",
                    "Time-sensitive offer with significant benefits."
                ],
                'ctas': [
                    "Please respond immediately to secure your spot.",
                    "Time is critical - please reply today to discuss next steps.",
                    "This requires immediate action - please contact me today.",
                    "Don't miss out - respond now to take advantage of this opportunity."
                ],
                'closings': [
                    "Best regards",
                    "Sincerely",
                    "Urgently yours"
                ]
            }
        }
        
        self.subject_templates = {
            'professional': [
                "{company} - Exclusive Opportunity",
                "Partnership Opportunity for {company}",
                "Growth Opportunity for {company}",
                "Innovation Partnership with {company}",
                "Strategic Opportunity for {company}"
            ],
            'casual': [
                "Quick question about {company}",
                "Something you might like",
                "Quick chat about {company}",
                "Thought you'd find this interesting",
                "Quick question for you"
            ],
            'urgent': [
                "URGENT: Limited Time Opportunity for {company}",
                "Time-Sensitive: {company} Growth Opportunity",
                "Action Required: {company} Partnership",
                "Immediate: {company} Exclusive Offer",
                "Deadline: {company} Opportunity"
            ]
        }
    
    def generate_email(self, lead_data: Dict, campaign_type: str = 'professional', 
                      custom_message: str = None) -> Dict[str, str]:
        """Generate personalized email content"""
        
        # Select template based on campaign type
        template = self.email_templates.get(campaign_type, self.email_templates['professional'])
        subject_template = self.subject_templates.get(campaign_type, self.subject_templates['professional'])
        
        # Generate subject line
        subject = random.choice(subject_template).format(
            name=lead_data.get('name', 'Valued Customer'),
            company=lead_data.get('company', 'Your Company')
        )
        
        # Generate email body
        if custom_message:
            body = custom_message
        else:
            greeting = random.choice(template['greetings']).format(name=lead_data.get('name', 'Valued Customer'))
            intro = random.choice(template['intros']).format(company=lead_data.get('company', 'your company'))
            body_text = random.choice(template['bodies']).format(
                name=lead_data.get('name', 'Valued Customer'),
                company=lead_data.get('company', 'your company'),
                title=lead_data.get('title', 'valued professional')
            )
            value_prop = random.choice(template['value_props'])
            cta = random.choice(template['ctas']).format(company=lead_data.get('company', 'your company'))
            closing = random.choice(template['closings'])
            
            sender_name = os.getenv('SENDER_NAME', 'Your Name')
            body = f"{greeting},\n\n{intro}\n\n{body_text}\n\n{value_prop}\n\n{cta}\n\n{closing},\n{sender_name}"
        
        # Personalize the content
        body = body.format(
            name=lead_data.get('name', 'Valued Customer'),
            company=lead_data.get('company', 'your company'),
            title=lead_data.get('title', 'valued professional'),
            industry=lead_data.get('industry', 'your industry')
        )
        
        return {
            'subject': subject,
            'body': body,
            'lead_name': lead_data.get('name', ''),
            'lead_email': lead_data.get('email', ''),
            'lead_company': lead_data.get('company', ''),
            'lead_title': lead_data.get('title', ''),
            'campaign_type': campaign_type,
            'generated_at': datetime.now().isoformat()
        }
    
    def generate_multiple_subjects(self, lead_data: Dict, campaign_type: str = 'professional', count: int = 5) -> List[str]:
        """Generate multiple subject line options"""
        template = self.subject_templates.get(campaign_type, self.subject_templates['professional'])
        subjects = []
        
        for _ in range(count):
            subject = random.choice(template).format(
                name=lead_data.get('name', 'Valued Customer'),
                company=lead_data.get('company', 'Your Company')
            )
            subjects.append(subject)
        
        return list(set(subjects))  # Remove duplicates
    
    def generate_email_variations(self, lead_data: Dict, campaign_type: str = 'professional', count: int = 3) -> List[Dict]:
        """Generate multiple email variations"""
        variations = []
        
        for _ in range(count):
            email = self.generate_email(lead_data, campaign_type)
            variations.append(email)
        
        return variations

# Global AI email generator instance
ai_email_generator = AIEmailGenerator()

"""
Base scraper class for all lead generation scrapers
Provides common functionality for retries, rate limiting, and data validation
"""

import time
import random
import requests
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from fake_useragent import UserAgent
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class LeadData:
    """Standardized lead data structure"""
    name: str
    address: str
    city: str
    country: str
    niche: str
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    source: str = ""
    scraped_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage"""
        return {
            'name': self.name,
            'address': self.address,
            'city': self.city,
            'country': self.country,
            'niche': self.niche,
            'phone': self.phone or '',
            'email': self.email or '',
            'website': self.website or '',
            'source': self.source,
            'scraped_at': self.scraped_at or ''
        }

class BaseScraper(ABC):
    """Base class for all lead scrapers"""
    
    def __init__(self, name: str, rate_limit_delay: float = 1.0):
        self.name = name
        self.rate_limit_delay = rate_limit_delay
        
        # Try to use fake-useragent, fallback to static UAs
        try:
            from fake_useragent import UserAgent
            self.ua = UserAgent()
            self._random_ua = None
        except Exception:
            self.ua = None
            self._random_ua = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_2) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16 Safari/605.1.15",
                "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
            ]
        
        self.session = requests.Session()
        self._setup_session()
    
    def _setup_session(self):
        """Setup session with headers and retry strategy"""
        ua_value = self.ua.random if self.ua else self._random_ua[0]
        self.session.headers.update({
            'User-Agent': ua_value,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
    
    def _get_random_delay(self) -> float:
        """Get random delay between requests to avoid detection"""
        base_delay = self.rate_limit_delay
        return base_delay + random.uniform(0, base_delay * 0.5)
    
    def _rotate_user_agent(self):
        """Rotate user agent to avoid detection"""
        if self.ua:
            self.session.headers['User-Agent'] = self.ua.random
        elif self._random_ua:
            import random
            self.session.headers['User-Agent'] = random.choice(self._random_ua)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((requests.exceptions.RequestException, requests.exceptions.Timeout))
    )
    def _make_request(self, url: str, params: Optional[Dict] = None, **kwargs) -> requests.Response:
        """Make HTTP request with retry logic"""
        try:
            # Add random delay
            time.sleep(self._get_random_delay())
            
            # Rotate user agent occasionally
            if random.random() < 0.3:
                self._rotate_user_agent()
            
            logger.info(f"Making request to {url} with params: {params}")
            response = self.session.get(url, params=params, timeout=30, **kwargs)
            logger.info(f"Response status: {response.status_code}, content length: {len(response.content)}")
            response.raise_for_status()
            return response
            
        except requests.exceptions.RequestException as e:
            logger.warning(f"Request failed for {self.name}: {e}")
            raise
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize text data"""
        if not text:
            return ""
        return ' '.join(text.strip().split())
    
    def _extract_phone(self, text: str) -> Optional[str]:
        """Extract phone number from text"""
        if not text:
            return None
        
        import re
        # Common phone number patterns
        phone_patterns = [
            r'\+?1?[-.\s]?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})',
            r'\+?[0-9]{1,4}[-.\s]?[0-9]{1,4}[-.\s]?[0-9]{1,4}[-.\s]?[0-9]{1,4}',
        ]
        
        for pattern in phone_patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(0).strip()
        return None
    
    def _extract_email(self, text: str) -> Optional[str]:
        """Extract email from text"""
        if not text:
            return None
        
        import re
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        match = re.search(email_pattern, text)
        return match.group(0) if match else None
    
    def _validate_lead(self, lead: LeadData) -> bool:
        """Validate lead data before returning"""
        return (
            lead.name and len(lead.name.strip()) > 2 and
            lead.address and len(lead.address.strip()) > 5 and
            lead.city and len(lead.city.strip()) > 1 and
            lead.country and len(lead.country.strip()) > 1 and
            lead.niche and len(lead.niche.strip()) > 2
        )
    
    @abstractmethod
    def search_leads(self, 
                    city: str, 
                    country: str, 
                    niche: str, 
                    business_name: Optional[str] = None,
                    limit: int = 50) -> List[LeadData]:
        """
        Search for leads based on criteria
        
        Args:
            city: City to search in
            country: Country to search in  
            niche: Industry/niche to search for
            business_name: Optional specific business name
            limit: Maximum number of leads to return
            
        Returns:
            List of LeadData objects
        """
        pass
    
    def __str__(self):
        return f"{self.name} Scraper"

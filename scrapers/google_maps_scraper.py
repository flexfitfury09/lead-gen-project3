"""
Google Maps scraper for business leads
Uses Google Maps search results to extract business information
"""

import re
import json
from typing import Dict, List, Optional
from bs4 import BeautifulSoup
import logging
from .base_scraper import BaseScraper, LeadData

class GoogleMapsScraper(BaseScraper):
    """Scraper for Google Maps business listings"""
    
    def __init__(self):
        super().__init__("Google Maps", rate_limit_delay=2.0)
        self.base_url = "https://www.google.com/maps/search"
        self._logger = logging.getLogger(__name__)
    
    def search_leads(self, 
                    city: str, 
                    country: str, 
                    niche: str, 
                    business_name: Optional[str] = None,
                    limit: int = 50) -> List[LeadData]:
        """Search for leads on Google Maps"""
        leads = []
        
        try:
            # Construct search query
            query_parts = [niche]
            if business_name:
                query_parts.append(business_name)
            query_parts.extend([city, country])
            
            search_query = " ".join(query_parts)
            
            # Search parameters
            params = {
                'q': search_query,
                'hl': 'en',
                'gl': country.lower()
            }
            
            self._logger.info(f"Searching Google Maps for: {search_query}")
            
            # Make request
            response = self._make_request(self.base_url, params=params)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract business data from JSON-LD structured data
            leads.extend(self._extract_from_json_ld(soup, city, country, niche))
            
            # Extract from HTML content
            leads.extend(self._extract_from_html(soup, city, country, niche))
            
            # Limit results
            leads = leads[:limit]
            
            self._logger.info(f"Found {len(leads)} leads from Google Maps")
            
        except Exception as e:
            self._logger.error(f"Error scraping Google Maps: {e}")
        
        return leads
    
    def _extract_from_json_ld(self, soup: BeautifulSoup, city: str, country: str, niche: str) -> List[LeadData]:
        """Extract business data from JSON-LD structured data"""
        leads = []
        
        try:
            # Look for JSON-LD scripts
            scripts = soup.find_all('script', type='application/ld+json')
            
            for script in scripts:
                try:
                    data = json.loads(script.string)
                    
                    if isinstance(data, dict):
                        lead = self._parse_json_ld_business(data, city, country, niche)
                        if lead and self._validate_lead(lead):
                            leads.append(lead)
                    elif isinstance(data, list):
                        for item in data:
                            lead = self._parse_json_ld_business(item, city, country, niche)
                            if lead and self._validate_lead(lead):
                                leads.append(lead)
                                
                except (json.JSONDecodeError, KeyError, TypeError):
                    continue
                    
        except Exception as e:
            self._logger.warning(f"Error extracting JSON-LD data: {e}")
        
        return leads
    
    def _parse_json_ld_business(self, data: Dict, city: str, country: str, niche: str) -> Optional[LeadData]:
        """Parse business data from JSON-LD"""
        try:
            # Check if this is a business/organization
            if data.get('@type') not in ['LocalBusiness', 'Organization', 'Store']:
                return None
            
            name = data.get('name', '')
            if not name:
                return None
            
            # Extract address
            address = ""
            if 'address' in data:
                addr = data['address']
                if isinstance(addr, dict):
                    address_parts = []
                    for field in ['streetAddress', 'addressLocality', 'addressRegion', 'postalCode']:
                        if field in addr and addr[field]:
                            address_parts.append(addr[field])
                    address = ', '.join(address_parts)
                elif isinstance(addr, str):
                    address = addr
            
            # Extract contact info
            phone = data.get('telephone', '')
            website = data.get('url', '')
            email = data.get('email', '')
            
            # If no address found, try to construct from location
            if not address and 'geo' in data:
                geo = data['geo']
                if isinstance(geo, dict) and 'latitude' in geo and 'longitude' in geo:
                    address = f"Coordinates: {geo['latitude']}, {geo['longitude']}"
            
            return LeadData(
                name=self._clean_text(name),
                address=self._clean_text(address) or f"{city}, {country}",
                city=city,
                country=country,
                niche=niche,
                phone=self._extract_phone(phone) if phone else None,
                email=self._extract_email(email) if email else None,
                website=website if website else None,
                source="Google Maps",
                scraped_at=self._get_timestamp()
            )
            
        except Exception as e:
            self._logger.warning(f"Error parsing JSON-LD business: {e}")
            return None
    
    def _extract_from_html(self, soup: BeautifulSoup, city: str, country: str, niche: str) -> List[LeadData]:
        """Extract business data from HTML content"""
        leads = []
        
        try:
            # Look for business listings in various containers
            selectors = [
                '[data-result-index]',
                '.Nv2PK',
                '.THOPZb',
                '.VkpGBb',
                '.lI9IFe'
            ]
            
            for selector in selectors:
                elements = soup.select(selector)
                
                for element in elements:
                    lead = self._parse_html_business(element, city, country, niche)
                    if lead and self._validate_lead(lead):
                        leads.append(lead)
                        
        except Exception as e:
            self._logger.warning(f"Error extracting HTML data: {e}")
        
        return leads
    
    def _parse_html_business(self, element, city: str, country: str, niche: str) -> Optional[LeadData]:
        """Parse business data from HTML element"""
        try:
            # Extract business name
            name_selectors = [
                '.fontHeadlineSmall',
                '.fontHeadlineMedium', 
                '.fontHeadlineLarge',
                'h3',
                '.qBF1Pd',
                '.fontTitleMedium'
            ]
            
            name = ""
            for selector in name_selectors:
                name_elem = element.select_one(selector)
                if name_elem and name_elem.get_text(strip=True):
                    name = name_elem.get_text(strip=True)
                    break
            
            if not name:
                return None
            
            # Extract address
            address_selectors = [
                '.W4Efsd',
                '.W4Efsd:last-child',
                '.fontBodyMedium',
                '.fontBodySmall'
            ]
            
            address = ""
            for selector in address_selectors:
                addr_elem = element.select_one(selector)
                if addr_elem:
                    addr_text = addr_elem.get_text(strip=True)
                    # Check if this looks like an address
                    if any(word in addr_text.lower() for word in ['street', 'st', 'avenue', 'ave', 'road', 'rd', 'drive', 'dr']):
                        address = addr_text
                        break
            
            # Extract phone
            phone = ""
            phone_elem = element.select_one('[href^="tel:"]')
            if phone_elem:
                phone = phone_elem.get('href', '').replace('tel:', '')
            
            # Extract website
            website = ""
            website_elem = element.select_one('[href^="http"]')
            if website_elem:
                website = website_elem.get('href', '')
            
            return LeadData(
                name=self._clean_text(name),
                address=self._clean_text(address) or f"{city}, {country}",
                city=city,
                country=country,
                niche=niche,
                phone=self._extract_phone(phone) if phone else None,
                email=None,  # Rarely available in Google Maps HTML
                website=website if website else None,
                source="Google Maps",
                scraped_at=self._get_timestamp()
            )
            
        except Exception as e:
            self._logger.warning(f"Error parsing HTML business: {e}")
            return None
    
    def _get_timestamp(self) -> str:
        """Get current timestamp"""
        from datetime import datetime
        return datetime.now().isoformat()

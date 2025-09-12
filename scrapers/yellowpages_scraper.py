"""
Yellow Pages scraper for business leads
Scrapes business listings from Yellow Pages search results
"""

import re
from typing import Dict, List, Optional
from bs4 import BeautifulSoup
import logging
from urllib.parse import quote_plus, urljoin
from .base_scraper import BaseScraper, LeadData

class YellowPagesScraper(BaseScraper):
    """Scraper for Yellow Pages business listings"""
    
    def __init__(self):
        super().__init__("Yellow Pages", rate_limit_delay=1.2)
        self.base_url = "https://www.yellowpages.com/search"
        self._logger = logging.getLogger(__name__)
    
    def search_leads(self, 
                    city: str, 
                    country: str, 
                    niche: str, 
                    business_name: Optional[str] = None,
                    limit: int = 50) -> List[LeadData]:
        """Search for leads on Yellow Pages"""
        leads = []
        
        try:
            # Construct search query
            query_parts = [niche]
            if business_name:
                query_parts.append(business_name)
            
            search_query = " ".join(query_parts)
            location = f"{city}, {country}"
            
            # Search parameters
            params = {
                'search_terms': search_query,
                'geo_location_terms': location
            }
            
            self._logger.info(f"Searching Yellow Pages for: {search_query} in {location}")
            
            # Make request
            response = self._make_request(self.base_url, params=params)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract business listings
            leads.extend(self._extract_business_listings(soup, city, country, niche))
            
            # Try to get more results from pagination
            if len(leads) < limit:
                leads.extend(self._scrape_additional_pages(soup, city, country, niche, limit - len(leads)))
            
            # Limit results
            leads = leads[:limit]
            
            self._logger.info(f"Found {len(leads)} leads from Yellow Pages")
            
        except Exception as e:
            self._logger.error(f"Error scraping Yellow Pages: {e}")
        
        return leads
    
    def _extract_business_listings(self, soup: BeautifulSoup, city: str, country: str, niche: str) -> List[LeadData]:
        """Extract business listings from search results page"""
        leads = []
        
        try:
            # Look for business listing containers
            listing_selectors = [
                '.result',
                '.search-result',
                '.listing',
                '.business-listing',
                '.srp-listing'
            ]
            
            listings = []
            for selector in listing_selectors:
                elements = soup.select(selector)
                if elements:
                    listings = elements
                    break
            
            # If no specific selectors found, try general approach
            if not listings:
                listings = soup.select('.v-card')
            
            for listing in listings:
                lead = self._parse_business_listing(listing, city, country, niche)
                if lead and self._validate_lead(lead):
                    leads.append(lead)
                    
        except Exception as e:
            self._logger.warning(f"Error extracting business listings: {e}")
        
        return leads
    
    def _parse_business_listing(self, element, city: str, country: str, niche: str) -> Optional[LeadData]:
        """Parse individual business listing"""
        try:
            # Extract business name
            name_selectors = [
                'h2 a',
                '.business-name a',
                'h3 a',
                '.listing-name a',
                '.result-title a',
                'a[data-track="listing-name"]'
            ]
            
            name = ""
            business_url = ""
            for selector in name_selectors:
                name_elem = element.select_one(selector)
                if name_elem:
                    name = name_elem.get_text(strip=True)
                    business_url = name_elem.get('href', '')
                    break
            
            if not name:
                return None
            
            # Extract address
            address_selectors = [
                '.adr',
                '.street-address',
                '.address',
                '.location',
                '.result-address',
                '.listing-address'
            ]
            
            address = ""
            for selector in address_selectors:
                addr_elem = element.select_one(selector)
                if addr_elem:
                    addr_text = addr_elem.get_text(strip=True)
                    # Clean up address text
                    addr_text = re.sub(r'\s+', ' ', addr_text)
                    if len(addr_text) > 10:  # Reasonable address length
                        address = addr_text
                        break
            
            # Extract phone number
            phone = ""
            phone_selectors = [
                '[href^="tel:"]',
                '.phone',
                '.phone-number',
                '.result-phone',
                '.listing-phone'
            ]
            
            for selector in phone_selectors:
                phone_elem = element.select_one(selector)
                if phone_elem:
                    phone_text = phone_elem.get_text(strip=True)
                    if not phone_text and phone_elem.get('href'):
                        phone_text = phone_elem.get('href', '').replace('tel:', '')
                    phone = phone_text
                    break
            
            # Extract website
            website = ""
            website_selectors = [
                'a[href*="http"]:not([href*="yellowpages.com"])',
                '.website-link a',
                '.result-website a',
                '.listing-website a'
            ]
            
            for selector in website_selectors:
                website_elem = element.select_one(selector)
                if website_elem:
                    href = website_elem.get('href', '')
                    if href and not href.startswith('#'):
                        website = href
                        break
            
            # Extract email (if available)
            email = ""
            email_selectors = [
                '[href^="mailto:"]',
                '.email',
                '.email-address'
            ]
            
            for selector in email_selectors:
                email_elem = element.select_one(selector)
                if email_elem:
                    email_text = email_elem.get_text(strip=True)
                    if not email_text and email_elem.get('href'):
                        email_text = email_elem.get('href', '').replace('mailto:', '')
                    email = email_text
                    break
            
            # Extract categories/tags
            categories = []
            category_selectors = [
                '.categories a',
                '.business-categories a',
                '.listing-categories a',
                '.result-categories a'
            ]
            
            for selector in category_selectors:
                cat_elems = element.select(selector)
                for cat_elem in cat_elems:
                    cat_text = cat_elem.get_text(strip=True)
                    if cat_text and len(cat_text) > 2 and cat_text not in categories:
                        categories.append(cat_text)
            
            # Use categories to refine niche if available
            refined_niche = niche
            if categories and niche.lower() not in ' '.join(categories).lower():
                # Try to find a category that matches our niche
                for cat in categories:
                    if any(word in cat.lower() for word in niche.lower().split()):
                        refined_niche = cat
                        break
            
            # Extract additional business info
            business_info = ""
            info_selectors = [
                '.business-info',
                '.listing-info',
                '.result-info',
                '.description'
            ]
            
            for selector in info_selectors:
                info_elem = element.select_one(selector)
                if info_elem:
                    business_info = info_elem.get_text(strip=True)
                    break
            
            return LeadData(
                name=self._clean_text(name),
                address=self._clean_text(address) or f"{city}, {country}",
                city=city,
                country=country,
                niche=refined_niche,
                phone=self._extract_phone(phone) if phone else None,
                email=self._extract_email(email) if email else None,
                website=website if website else None,
                source="Yellow Pages",
                scraped_at=self._get_timestamp()
            )
            
        except Exception as e:
            self._logger.warning(f"Error parsing business listing: {e}")
            return None
    
    def _scrape_additional_pages(self, soup: BeautifulSoup, city: str, country: str, niche: str, remaining_limit: int) -> List[LeadData]:
        """Scrape additional pages for more results"""
        leads = []
        
        try:
            # Look for pagination links
            next_page_selectors = [
                'a[aria-label="Next"]',
                '.pagination a[href*="page="]',
                '.next-page a',
                'a[href*="page="]'
            ]
            
            next_url = None
            for selector in next_page_selectors:
                next_elem = soup.select_one(selector)
                if next_elem:
                    next_url = next_elem.get('href')
                    break
            
            if next_url and remaining_limit > 0:
                # Make request to next page
                if next_url.startswith('/'):
                    next_url = f"https://www.yellowpages.com{next_url}"
                
                response = self._make_request(next_url)
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Extract more listings
                additional_leads = self._extract_business_listings(soup, city, country, niche)
                leads.extend(additional_leads[:remaining_limit])
                
        except Exception as e:
            self._logger.warning(f"Error scraping additional pages: {e}")
        
        return leads
    
    def _get_timestamp(self) -> str:
        """Get current timestamp"""
        from datetime import datetime
        return datetime.now().isoformat()

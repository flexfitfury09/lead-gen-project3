"""
Yelp scraper for business leads
Scrapes business listings from Yelp search results
"""

import re
from typing import Dict, List, Optional
from bs4 import BeautifulSoup
import logging
from urllib.parse import quote_plus, urljoin
from .base_scraper import BaseScraper, LeadData

class YelpScraper(BaseScraper):
    """Scraper for Yelp business listings"""
    
    def __init__(self):
        super().__init__("Yelp", rate_limit_delay=1.5)
        self.base_url = "https://www.yelp.com/search"
        self._logger = logging.getLogger(__name__)
    
    def search_leads(self, 
                    city: str, 
                    country: str, 
                    niche: str, 
                    business_name: Optional[str] = None,
                    limit: int = 50) -> List[LeadData]:
        """Search for leads on Yelp"""
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
                'find_desc': search_query,
                'find_loc': location,
                'ns': '1'  # Sort by relevance
            }
            
            self._logger.info(f"Searching Yelp for: {search_query} in {location}")
            
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
            
            self._logger.info(f"Found {len(leads)} leads from Yelp")
            
        except Exception as e:
            self._logger.error(f"Error scraping Yelp: {e}")
        
        return leads
    
    def _extract_business_listings(self, soup: BeautifulSoup, city: str, country: str, niche: str) -> List[LeadData]:
        """Extract business listings from search results page"""
        leads = []
        
        try:
            # Look for business listing containers
            listing_selectors = [
                '[data-testid="serp-ia-card"]',
                '.container__09f24__mpR8_',
                '.mainAttributes__09f24__mrQp8',
                '.businessName__09f24__3Ml0X'
            ]
            
            listings = []
            for selector in listing_selectors:
                elements = soup.select(selector)
                if elements:
                    listings = elements
                    break
            
            # If no specific selectors found, try general approach
            if not listings:
                listings = soup.select('.searchResult')
            
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
                'h3 a',
                '.businessName__09f24__3Ml0X a',
                'h4 a',
                '.css-1m051bw a',
                'a[href*="/biz/"]'
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
                '.css-1e4fdj9',
                '.css-1e4fdj9 p',
                '.secondaryAttributes__09f24__3Ml0X',
                '.address__09f24__3Ml0X'
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
                '.css-1e4fdj9 a[href^="tel:"]'
            ]
            
            for selector in phone_selectors:
                phone_elem = element.select_one(selector)
                if phone_elem:
                    phone = phone_elem.get('href', '').replace('tel:', '')
                    break
            
            # Extract website
            website = ""
            website_selectors = [
                'a[href*="biz.yelp.com"]',
                'a[href*="yelp.com/biz"]'
            ]
            
            for selector in website_selectors:
                website_elem = element.select_one(selector)
                if website_elem:
                    href = website_elem.get('href', '')
                    if href.startswith('/'):
                        website = f"https://www.yelp.com{href}"
                    else:
                        website = href
                    break
            
            # Extract rating and review info (for additional context)
            rating_elem = element.select_one('[aria-label*="star"]')
            rating = ""
            if rating_elem:
                rating = rating_elem.get('aria-label', '')
            
            # Extract categories/tags
            categories = []
            category_selectors = [
                '.css-1e4fdj9 span',
                '.css-1e4fdj9 a'
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
            
            return LeadData(
                name=self._clean_text(name),
                address=self._clean_text(address) or f"{city}, {country}",
                city=city,
                country=country,
                niche=refined_niche,
                phone=self._extract_phone(phone) if phone else None,
                email=None,  # Yelp doesn't typically show emails
                website=website if website else None,
                source="Yelp",
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
                '.css-1m051bw a[href*="start="]',
                'a[href*="start="]'
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
                    next_url = f"https://www.yelp.com{next_url}"
                
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

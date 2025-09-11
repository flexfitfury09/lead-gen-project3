"""
LinkedIn scraper for business leads
Scrapes public business pages from LinkedIn (no login required)
Uses Bing search to find LinkedIn company pages
"""

import re
from typing import Dict, List, Optional
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urljoin
from .base_scraper import BaseScraper, LeadData

class LinkedInScraper(BaseScraper):
    """Scraper for LinkedIn business pages via Bing search"""
    
    def __init__(self):
        super().__init__("LinkedIn", rate_limit_delay=2.5)
        self.base_url = "https://www.bing.com/search"
    
    def search_leads(self, 
                    city: str, 
                    country: str, 
                    niche: str, 
                    business_name: Optional[str] = None,
                    limit: int = 50) -> List[LeadData]:
        """Search for leads on LinkedIn via Bing"""
        leads = []
        
        try:
            # Construct search query for LinkedIn company pages
            query_parts = [niche]
            if business_name:
                query_parts.append(business_name)
            
            # Add LinkedIn site filter
            search_query = f"site:linkedin.com/company {' '.join(query_parts)} {city} {country}"
            
            # Search parameters
            params = {
                'q': search_query,
                'count': '50',
                'first': '1'
            }
            
            logger.info(f"Searching LinkedIn via Bing for: {search_query}")
            
            # Make request
            response = self._make_request(self.base_url, params=params)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract LinkedIn company links
            company_links = self._extract_company_links(soup)
            
            # Scrape each company page
            for link in company_links[:limit]:
                try:
                    lead = self._scrape_company_page(link, city, country, niche)
                    if lead and self._validate_lead(lead):
                        leads.append(lead)
                except Exception as e:
                    logger.warning(f"Error scraping company page {link}: {e}")
                    continue
            
            logger.info(f"Found {len(leads)} leads from LinkedIn")
            
        except Exception as e:
            logger.error(f"Error scraping LinkedIn: {e}")
        
        return leads
    
    def _extract_company_links(self, soup: BeautifulSoup) -> List[str]:
        """Extract LinkedIn company page links from Bing search results"""
        links = []
        
        try:
            # Look for search result links
            result_selectors = [
                '.b_algo h2 a',
                '.b_title a',
                '.b_caption a',
                'h2 a[href*="linkedin.com/company"]'
            ]
            
            for selector in result_selectors:
                elements = soup.select(selector)
                for element in elements:
                    href = element.get('href', '')
                    if 'linkedin.com/company/' in href:
                        # Clean up the URL
                        if '?' in href:
                            href = href.split('?')[0]
                        if href not in links:
                            links.append(href)
            
            # Also look for general links that might be LinkedIn company pages
            all_links = soup.select('a[href*="linkedin.com/company"]')
            for link in all_links:
                href = link.get('href', '')
                if 'linkedin.com/company/' in href:
                    if '?' in href:
                        href = href.split('?')[0]
                    if href not in links:
                        links.append(href)
                        
        except Exception as e:
            logger.warning(f"Error extracting company links: {e}")
        
        return links
    
    def _scrape_company_page(self, url: str, city: str, country: str, niche: str) -> Optional[LeadData]:
        """Scrape individual LinkedIn company page"""
        try:
            # Make request to company page
            response = self._make_request(url)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract company name
            name_selectors = [
                'h1',
                '.org-top-card-summary__title',
                '.org-top-card-summary__title h1',
                '.top-card-layout__title',
                '.company-name'
            ]
            
            name = ""
            for selector in name_selectors:
                name_elem = soup.select_one(selector)
                if name_elem:
                    name = name_elem.get_text(strip=True)
                    break
            
            if not name:
                return None
            
            # Extract company description/industry
            description_selectors = [
                '.org-top-card-summary__tagline',
                '.org-top-card-summary__info-item',
                '.company-description',
                '.top-card-layout__headline'
            ]
            
            description = ""
            for selector in description_selectors:
                desc_elem = soup.select_one(selector)
                if desc_elem:
                    description = desc_elem.get_text(strip=True)
                    break
            
            # Extract website
            website = ""
            website_selectors = [
                'a[href^="http"]:not([href*="linkedin.com"])',
                '.org-top-card-summary__website a',
                '.company-website a'
            ]
            
            for selector in website_selectors:
                website_elem = soup.select_one(selector)
                if website_elem:
                    website = website_elem.get('href', '')
                    break
            
            # Extract location/address
            location_selectors = [
                '.org-top-card-summary__info-item',
                '.company-location',
                '.top-card-layout__first-subline'
            ]
            
            location = ""
            for selector in location_selectors:
                loc_elem = soup.select_one(selector)
                if loc_elem:
                    loc_text = loc_elem.get_text(strip=True)
                    # Check if this looks like a location
                    if any(word in loc_text.lower() for word in ['city', 'state', 'country', 'united states', 'usa', 'canada', 'uk', 'australia']):
                        location = loc_text
                        break
            
            # Extract company size/industry info
            company_info = ""
            info_selectors = [
                '.org-top-card-summary__info-item',
                '.company-info',
                '.top-card-layout__second-subline'
            ]
            
            for selector in info_selectors:
                info_elems = soup.select(selector)
                for info_elem in info_elems:
                    info_text = info_elem.get_text(strip=True)
                    if info_text and len(info_text) > 5:
                        company_info += info_text + " "
            
            # Try to extract phone/email from company info
            phone = self._extract_phone(company_info)
            email = self._extract_email(company_info)
            
            # Use description or company info to refine niche
            refined_niche = niche
            if description:
                # Look for industry keywords in description
                industry_keywords = ['technology', 'software', 'healthcare', 'finance', 'retail', 'manufacturing', 'consulting', 'services']
                for keyword in industry_keywords:
                    if keyword in description.lower():
                        refined_niche = keyword.title()
                        break
            
            return LeadData(
                name=self._clean_text(name),
                address=self._clean_text(location) or f"{city}, {country}",
                city=city,
                country=country,
                niche=refined_niche,
                phone=phone,
                email=email,
                website=website if website else None,
                source="LinkedIn",
                scraped_at=self._get_timestamp()
            )
            
        except Exception as e:
            logger.warning(f"Error scraping company page {url}: {e}")
            return None
    
    def _get_timestamp(self) -> str:
        """Get current timestamp"""
        from datetime import datetime
        return datetime.now().isoformat()

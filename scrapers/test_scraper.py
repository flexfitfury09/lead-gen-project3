"""
Test scraper that returns mock data to verify the system works
"""

from typing import Dict, List, Optional
from .base_scraper import BaseScraper, LeadData

class TestScraper(BaseScraper):
    """Test scraper that returns mock data"""
    
    def __init__(self):
        super().__init__("Test Scraper", rate_limit_delay=0.1)
    
    def search_leads(self, 
                    city: str, 
                    country: str, 
                    niche: str, 
                    business_name: Optional[str] = None,
                    limit: int = 50) -> List[LeadData]:
        """Return mock test data"""
        logger.info(f"Test scraper searching for: {niche} in {city}, {country}")
        
        # Generate mock leads
        mock_leads = []
        for i in range(min(5, limit)):  # Return 5 test leads
            lead = LeadData(
                name=f"Test Business {i+1}",
                address=f"{100+i} Main St, {city}, {country}",
                city=city,
                country=country,
                niche=niche,
                phone=f"+1-555-{1000+i:04d}",
                email=f"contact{i+1}@testbusiness{i+1}.com",
                website=f"https://testbusiness{i+1}.com",
                source="Test Scraper",
                scraped_at=self._get_timestamp()
            )
            mock_leads.append(lead)
        
        logger.info(f"Test scraper returning {len(mock_leads)} mock leads")
        return mock_leads
    
    def _get_timestamp(self) -> str:
        """Get current timestamp"""
        from datetime import datetime
        return datetime.now().isoformat()

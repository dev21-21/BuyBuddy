# utils/affiliate.py
import base64
from urllib.parse import urlencode, urlparse, parse_qs, urlunparse

class AffiliateConverter:
    """Converts product URLs to affiliate links (EarnKaro-style)"""
    
    # Affiliate IDs/Tags per platform (You need to sign up and get these)
    AFFILIATE_CONFIG = {
        'amazon.in': {'tag': 'earnkaro-21'},  # Replace with YOUR Amazon Associates tag
        'amazon.com': {'tag': 'buybuddy-20'},  # US version
        'flipkart.com': {'affid': 'roo7t0', 'source': 'buybuddy'},  # Replace with YOUR Flipkart affiliate ID
        'myntra.com': {'affid': 'buybuddy'},
        'ajio.com': {'affid': 'buybuddy'},
        'nykaa.com': {'affid': 'buybuddy'},
        'ajio.com': {'affid': 'buybuddy'},
    }

    @staticmethod
    def convert(original_url: str) -> str:
        """Convert product URL to affiliate link."""
        if not original_url:
            return original_url

        try:
            parsed = urlparse(original_url)
            domain = parsed.netloc.lower()

            # 1. Amazon.in Affiliate (Most Common in India)
            if 'amazon.in' in domain or 'amazon.com' in domain:
                return AffiliateConverter._amazon_affiliate(original_url, domain)

            # 2. Flipkart Affiliate
            elif 'flipkart.com' in domain or 'fkrt.it' in domain:
                return AffiliateConverter._flipkart_affiliate(original_url)

            # 3. Myntra
            elif 'myntra.com' in domain:
                return AffiliateConverter._generic_affiliate(original_url, 'myntra.com', 'affid')

            # 4. AJIO
            elif 'ajio.com' in domain:
                return AffiliateConverter._generic_affiliate(original_url, 'ajio.com', 'affid')

            # 5. Nykaa
            elif 'nykaa.com' in domain:
                return AffiliateConverter._generic_affiliate(original_url, 'nykaa.com', 'affid')

            # 6. Generic Fallback: Redirect via EarnKaro Gateway
            else:
                return AffiliateConverter._earnkaro_gateway(original_url)

        except Exception as e:
            print(f"⚠️ Affiliate conversion failed: {e}")
            return original_url

    @staticmethod
    def _amazon_affiliate(url: str, domain: str) -> str:
        """Inject Amazon Associates tag."""
        parsed = urlparse(url)
        tag = AffiliateConverter.AFFILIATE_CONFIG['amazon.in' if 'amazon.in' in domain else 'amazon.com']['tag']

        # Preserve existing params, add/replace 'tag'
        params = parse_qs(parsed.query, keep_blank_values=True)
        params['tag'] = [tag]  # parse_qs returns lists
        new_query = urlencode(params, doseq=True)

        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))

    @staticmethod
    def _flipkart_affiliate(url: str) -> str:
        """Inject Flipkart affiliate ID."""
        # Flipkart uses shortlinks (fkrt.it) which already have affiliate ID baked in
        # For full URLs, append affiliate params
        if 'fkrt.it' in url:
            # Already a shortlink, return as-is (affiliate ID embedded)
            return url

        # Full flipkart.com URL
        parsed = urlparse(url)
        affid = AffiliateConverter.AFFILIATE_CONFIG['flipkart.com']['affid']
        
        params = parse_qs(parsed.query, keep_blank_values=True)
        params['affid'] = [affid]
        params['affSource'] = ['buybuddy']
        new_query = urlencode(params, doseq=True)

        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))

    @staticmethod
    def _generic_affiliate(url: str, domain: str, param_name: str) -> str:
        """Generic affiliate injection for Myntra, AJIO, etc."""
        parsed = urlparse(url)
        affid = AffiliateConverter.AFFILIATE_CONFIG.get(domain, {}).get('affid', 'buybuddy')

        params = parse_qs(parsed.query, keep_blank_values=True)
        params[param_name] = [affid]
        new_query = urlencode(params, doseq=True)

        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))

    @staticmethod
    def _earnkaro_gateway(url: str) -> str:
        """
        Fallback: Route unknown sites via EarnKaro's redirect gateway.
        Format: https://earnkaro.com/go?url=<base64_encoded_url>&ref=buybuddy
        """
        encoded_url = base64.b64encode(url.encode()).decode()
        return f"https://earnkaro.com/go?url={encoded_url}&ref=buybuddy"
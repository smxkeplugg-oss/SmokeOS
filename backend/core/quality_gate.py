import re
from typing import Dict, Any, List

class QualityGate:
    """
    Quality Gate for Web Development Output Validation.
    Ensures zero 'AI slop' and professional-grade, responsive, accessible code.
    """
    def __init__(self) -> None:
        self.rules = [
            self._check_accessibility,
            self._check_responsiveness,
            self._check_ai_slop,
            self._check_semantic_html,
            self._check_vibe_consistency,
            self._check_u18_safety
        ]
        
    def validate_code(self, code: str, file_type: str = "html") -> Dict[str, Any]:
        """Run all quality checks on the generated code."""
        issues = []
        passed = True
        
        for rule in self.rules:
            result = rule(code, file_type)
            if not result['passed']:
                passed = False
                issues.extend(result['issues'])
                
        return {
            "passed": passed,
            "issues": issues,
            "score": 10 - len(issues) if len(issues) <= 10 else 0
        }
        
    def _check_accessibility(self, code: str, file_type: str) -> Dict[str, Any]:
        """Check for basic accessibility standards (e.g., alt tags, aria labels)."""
        issues = []
        if file_type in ["html", "tsx", "jsx"]:
            # Check for missing alt attributes on images
            img_tags = re.findall(r'<img[^>]*>', code)
            for img in img_tags:
                if 'alt=' not in img:
                    issues.append(f"Missing alt attribute in image tag: {img}")
                    
            # Check for empty links
            a_tags = re.findall(r'<a[^>]*>.*?</a>', code, re.DOTALL)
            for a in a_tags:
                if not re.search(r'>\s*\S+\s*<', a) and 'aria-label' not in a:
                    issues.append(f"Empty link without aria-label: {a}")
                    
        return {"passed": len(issues) == 0, "issues": issues}
        
    def _check_responsiveness(self, code: str, file_type: str) -> Dict[str, Any]:
        """Ensure responsive design patterns are used (e.g., Tailwind classes)."""
        issues = []
        if file_type in ["html", "tsx", "jsx", "css"]:
            # Check for hardcoded widths/heights that might break responsiveness
            if re.search(r'width:\s*\d+px', code) or re.search(r'w-\[\d+px\]', code):
                issues.append("Hardcoded pixel widths detected. Use responsive classes (e.g., w-full, max-w-md, sm:w-1/2).")
                
            # Check for viewport meta tag in HTML
            if file_type == "html" and '<meta name="viewport"' not in code:
                issues.append("Missing viewport meta tag for mobile responsiveness.")
                
        return {"passed": len(issues) == 0, "issues": issues}
        
    def _check_ai_slop(self, code: str, file_type: str) -> Dict[str, Any]:
        """Detect common 'AI slop' patterns (e.g., generic placeholder text, overused gradients)."""
        issues = []
        slop_patterns = [
            r'Lorem ipsum',
            r'Welcome to my website',
            r'bg-gradient-to-r from-purple-400 via-pink-500 to-red-500', # The classic AI gradient
            r'bg-gradient-to-br from-indigo-500 via-purple-500 to-pink-500', # Another overused one
            r'<!-- Add your content here -->',
            r'Your company name',
            r'Click here to learn more'
        ]
        
        for pattern in slop_patterns:
            if re.search(pattern, code, re.IGNORECASE):
                issues.append(f"Detected potential 'AI slop' pattern: {pattern}")
                
        return {"passed": len(issues) == 0, "issues": issues}

    def _check_vibe_consistency(self, code: str, file_type: str) -> Dict[str, Any]:
        """Ensure consistent design vibe (e.g., don't mix brutalist with soft organic)."""
        issues = []
        if file_type in ["html", "tsx", "jsx"]:
            has_brutalist = "border-black" in code or "shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]" in code
            has_soft = "rounded-3xl" in code or "shadow-xl" in code or "backdrop-blur" in code
            
            if has_brutalist and has_soft:
                issues.append("Conflicting design vibes detected: Mixing brutalist (thick borders) with soft organic (large rounded corners/blur).")
        
        return {"passed": len(issues) == 0, "issues": issues}
        
    def _check_semantic_html(self, code: str, file_type: str) -> Dict[str, Any]:
        """Ensure semantic HTML tags are used instead of just divs."""
        issues = []
        if file_type in ["html", "tsx", "jsx"]:
            # Check if there are too many divs and no semantic tags
            div_count = len(re.findall(r'<div', code))
            semantic_tags = ['<header', '<main', '<footer', '<article', '<section', '<nav']
            semantic_count = sum(len(re.findall(tag, code)) for tag in semantic_tags)
            
            if div_count > 10 and semantic_count == 0:
                issues.append("High div count with no semantic HTML tags detected. Use <header>, <main>, <section>, etc.")
                
        return {"passed": len(issues) == 0, "issues": issues}

    def _check_u18_safety(self, code: str, file_type: str) -> Dict[str, Any]:
        """Check for U18 safety violations (e.g., inappropriate content, harmful links)."""
        issues = []
        # Check for inappropriate keywords or patterns
        harmful_patterns = [
            r'sexually explicit',
            r'self-harm',
            r'violence',
            r'illegal acts',
            r'gambling',
            r'alcohol',
            r'tobacco'
        ]
        for pattern in harmful_patterns:
            if re.search(pattern, code, re.IGNORECASE):
                issues.append(f"U18 Safety Violation: Detected harmful pattern: {pattern}")
        
        return {"passed": len(issues) == 0, "issues": issues}

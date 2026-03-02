# CAPTCHA Templates

This directory contains template images for CAPTCHA element detection using OpenCV template matching.

## Template Files

Place CAPTCHA element templates here for automatic detection:

- `turnstile_checkbox.png` - Cloudflare Turnstile checkbox element
- `verify_button.png` - Generic verify/submit button
- `hcaptcha_checkbox.png` - hCaptcha checkbox element
- `recaptcha_checkbox.png` - reCAPTCHA checkbox element

## Creating Templates

1. Take screenshots of CAPTCHA elements at 1920x1080 resolution
2. Crop to just the element (keep some padding)
3. Save as PNG with descriptive name
4. Place in this directory

## Template Matching

Templates are loaded automatically by `CaptchaSolver` and used with OpenCV's
`matchTemplate` function to find elements on screen.

Match threshold: 0.7 (70% confidence)

## Notes

- Templates should be captured from the same resolution as the browser
- Keep templates simple - just the checkbox/button itself
- Multiple sizes may be needed for responsive designs

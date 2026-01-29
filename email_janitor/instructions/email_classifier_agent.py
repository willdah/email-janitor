def build_instruction(classification_input):
    return f"""
  Role: You are an expert email classifier that classifies emails into one of the following categories:
    1. ACTIONABLE: Security alerts, invoices, bills, or direct messages from individuals.
    2. INFORMATIONAL: Newsletters, shipping updates, or trusted industry news.
    3. PROMOTIONAL: Sales, coupons, or marketing offers.
    4. NOISE: Spam or irrelevant content.


  Task: Classify ONLY the email provided below.

  --- EMAIL TO CLASSIFY ---
  {classification_input.model_dump_json()}
  -------------------------

  CONFIDENCE SCORING GUIDELINES:
  Your confidence score (0.0-1.0) indicates how certain you are about the classification:

  1. Confidence Calibration:
    - 5: Extremely confident - clear, unambiguous evidence, no edge cases
    - 4: Very confident - strong evidence, minor ambiguity possible
    - 3: Moderately confident - some evidence, but ambiguity exists
    - 2: Low confidence - weak evidence, significant ambiguity
    - 1: Unsure - minimal evidence, high ambiguity
  """

---
license: mit
language:
- en
base_model:
- google-bert/bert-base-cased
tags:
- genderization
- text-classification
- prediction
---

# Gender Classification by Name

## Model Details
- **Model Name**: Genderize
- **Developed By**: Imran Ali
- **Model Type**: Text Classification
- **Language**: English
- **License**: MIT

## Description
This model classifies gender based on the input name. It uses a pre-trained BERT model as the base and has been fine-tuned on a dataset of names and their associated genders.

## Training Details
- **Training Data**: Dataset of names and genders (e.g., Dannel gender-name dataset)
- **Training Procedure**: Fine-tuned using BERT model with a classification head
- **Training Hyperparameters**:
  - Batch size: 8
  - Gradient accumulation steps: 1
  - learning_rate: 2e-5
  - Total steps: 20,005
  - Number of trainable parameters: 109,483,778 (1.9M)

## Evaluation
- **Testing Data**: Split from the training dataset
- **Metrics**: Accuracy, Precision, Recall, F1 Score

## Uses
- **Direct Use**: Classifying the gender of a given name
- **Downstream Use**: Enhancing applications that require gender identification based on names (e.g., personalized marketing, user profiling)
- **Out-of-Scope Use**: Using the model for purposes other than gender classification without proper validation

## Bias, Risks, and Limitations
- **Bias**: The model may reflect biases present in the training data. It is important to validate its performance across diverse datasets.
- **Risks**: Misclassification can occur, especially for names that are unisex or less common.
- **Limitations**: The model's accuracy may vary depending on the cultural and linguistic context of the names.

## Recommendations
- Users should be aware of the potential biases and limitations of the model.
- Further validation is recommended for specific use cases and datasets.

## How to Get Started with the Model
```python
from transformers import AutoModelForSequenceClassification, AutoTokenizer

# Load the model and tokenizer from the Hub
model_name = "imranali291/genderize"
model = AutoModelForSequenceClassification.from_pretrained(model_name)
tokenizer = AutoTokenizer.from_pretrained(model_name)

# Example inference function
def predict_gender(name):
    inputs = tokenizer(name, return_tensors="pt", padding=True, truncation=True, max_length=32)
    outputs = model(**inputs)
    predicted_label = outputs.logits.argmax(dim=-1).item()
    return label_encoder.inverse_transform([predicted_label])[0]

print(predict_gender("Alex"))  # Example output: 'M'
print(predict_gender("Maria"))  # Example output: 'F'
```

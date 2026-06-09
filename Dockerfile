# Apify Actor - PagineGialle.it Scraper
FROM apify/actor-python:3.12

WORKDIR /usr/src/app

# Copy and install dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . ./

CMD ["python", "-m", "src"]

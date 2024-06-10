from flask import Flask, request, jsonify, render_template, session
from pymongo import MongoClient
import qrcode
import os
import random
from bson import ObjectId
import math
from geopy.distance import geodesic
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'supersecretkey'  # Needed for session management

# Connect to MongoDB
client = MongoClient('mongodb://localhost:27017/')
db = client['whatsapp_bot']

url = 'http://127.0.0.1:5000/create_order'
data = {
    "user_id": "123",
    "dishes": [
        {"dish_id": "456", "quantity": 2},
        {"dish_id": "789", "quantity": 1}
    ],
    "total_price": 25.5,
    "delivery_address": {
        "street": "123 Main St",
        "city": "Anytown",
        "pin_code": "12345",
        "google_pin_customer": "XYZ123",
        "google_pin_restaurant": "ABC456"
    }
}

@app.route('/')
def home():
    return "Hello, World!"

@app.route('/generate_qr')
def generate_qr():
    qr_url = "http://127.0.0.1:5000/start_chat"
    qr = qrcode.make(qr_url)
    qr_path = os.path.join(os.getcwd(), "static/qr_code.png")
    if not os.path.exists(os.path.dirname(qr_path)):
        os.makedirs(os.path.dirname(qr_path))
    qr.save(qr_path)
    return f"QR code generated at <a href='/static/qr_code.png' target='_blank'>/static/qr_code.png</a>"

@app.route('/start_chat', methods=['GET'])
def start_chat():
    return render_template('chat.html')

@app.route('/check_user', methods=['POST'])
def check_user():
    phone_number = request.json.get('phone_number')
    user = db.users.find_one({"phone_number": phone_number})
    if user:
        user['_id'] = str(user['_id'])  # Convert ObjectId to string
        return jsonify({"status": "returning", "user": user})
    else:
        return jsonify({"status": "new", "message": "Please provide your preferences"})

@app.route('/add_user', methods=['POST'])
def add_user():
    user_data = request.json
    db.users.insert_one(user_data)
    return jsonify({"status": "success"})

@app.route('/user_query', methods=['POST'])
def user_query():
    user_input = request.json.get('query')
    response = simulate_llm_response(user_input)
    return jsonify({"response": response})


@app.route('/add_restaurant', methods=['POST'])
def add_restaurant():
    resto_data = request.json
    db.restaurants.insert_one(resto_data)
    return jsonify({"status": "success"})

@app.route('/get_restaurants', methods=['GET'])
def get_restaurants():
    resto_list = list(db.restaurants.find())
    for resto in resto_list:
        resto['_id'] = str(resto['_id'])  # Convert ObjectId to string
    return jsonify(resto_list)

@app.route('/get_restaurant/<resto_id>', methods=['GET'])
def get_restaurant(resto_id):
    try:
        resto = db.restaurants.find_one({"_id": ObjectId(resto_id)})
        if resto:
            resto['_id'] = str(resto['_id'])  # Convert ObjectId to string
            return jsonify(resto)
        return jsonify({"status": "error", "message": "Restaurant not found"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/update_restaurant/<resto_id>', methods=['PUT'])
def update_restaurant(resto_id):
    try:
        resto_data = request.json
        db.restaurants.update_one({"_id": ObjectId(resto_id)}, {"$set": resto_data})
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/delete_restaurant/<resto_id>', methods=['DELETE'])
def delete_restaurant(resto_id):
    try:
        db.restaurants.delete_one({"_id": ObjectId(resto_id)})
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})
    
@app.route('/create_order', methods=['POST'])
def create_order():
    try:
        order_data = request.json
        if not order_data.get('user_id') or not order_data.get('dishes') or not order_data.get('delivery_address'):
            return jsonify({"status": "error", "message": "Incomplete order data"})
        
        # Calculate distance between customer and restaurant using Google PINs
        google_pin_customer = order_data['delivery_address'].get('google_pin_customer')
        google_pin_restaurant = order_data.get('google_pin_restaurant')
        if not google_pin_customer or not google_pin_restaurant:
            return jsonify({"status": "error", "message": "Google PINs are required for distance calculation"})
        
        customer_loc = db.locations.find_one({"google_pin": google_pin_customer})
        resto_loc = db.locations.find_one({"google_pin": google_pin_restaurant})
        
        if not customer_loc or not resto_loc:
            return jsonify({"status": "error", "message": "Location details not found for Google PINs"})
        
        customer_coords = (customer_loc['lat'], customer_loc['lng'])
        resto_coords = (resto_loc['lat'], resto_loc['lng'])
        distance_km = geodesic(customer_coords, resto_coords).kilometers
        
        # Fetch restaurant details
        resto_id = order_data.get('resto_id')
        restaurant = db.restaurants.find_one({"_id": ObjectId(resto_id)})
        if not restaurant:
            return jsonify({"status": "error", "message": "Restaurant details not found"})
        
        # Insert order data into the database
        order_data['distance_km'] = distance_km
        order_data['resto_details'] = restaurant
        order_data['timestamp'] = datetime.now()
        
        order_id = db.orders.insert_one(order_data).inserted_id
        return jsonify({"status": "success", "order_id": str(order_id)})
    
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/update_order/<order_id>', methods=['PUT'])
def update_order(order_id):
    try:
        order_data = request.json
        db.orders.update_one({"_id": ObjectId(order_id)}, {"$set": order_data})
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/confirm_order', methods=['POST'])
def confirm_order():
    try:
        order_id = session.get('order_id')
        if not order_id:
            return jsonify({"status": "error", "message": "No order in progress"})
        
        order = db.orders.find_one({"_id": ObjectId(order_id)})
        if order:
            payment_url = f"http://payment-gateway.com/pay?amount={order['total_price']}"
            qr = qrcode.make(payment_url)
            qr_path = os.path.join(os.getcwd(), "static/payment_qr.png")
            qr.save(qr_path)
            session.pop('order_id', None)  # Clear order ID from session after confirmation
            return jsonify({"status": "success", "qr_code_path": qr_path})
        return jsonify({"status": "error", "message": "Order not found"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

# Simulate LLM response function
def simulate_llm_response(user_input):
    user_input_lower = user_input.lower()

    # Logic for complex mixed-language queries
    if any(keyword in user_input_lower for keyword in ["sweet", "meetha", "मीठा"]):
        return "Sure! You might enjoy something from 'Sweet Tooth'. Here are some options: Gulab Jamun, Jalebi."
    elif any(keyword in user_input_lower for keyword in ["spicy", "chatpata", "चटपटा"]):
        if "chinese" in user_input_lower or "चाइनीज" in user_input_lower:
            # Example query for fetching dishes
            preference = "chinese spicy"
            dishes = fetch_dishes_by_preference(preference)
            return dishes if dishes else "Sorry, no spicy Chinese dishes available."
        return "What would you like to order today? We have Chinese, South Indian, and more."
    elif any(keyword in user_input_lower for keyword in ["chinese", "चाइनीज"]):
        return "Please choose a restaurant to see the menu."
    elif any(keyword in user_input_lower for keyword in ["menu", "मेनू"]):
        return "Please choose a restaurant to see the menu."
    elif any(keyword in user_input_lower for keyword in ["restaurants", "रेस्टोरेंट"]):
        return list_restaurants()
    elif any(keyword in user_input_lower for keyword in ["hello", "hi", "नमस्ते", "हैलो"]):
        return "Hello! How can I assist you today?"
    elif any(keyword in user_input_lower for keyword in ["thanks", "thank you", "धन्यवाद", "शुक्रिया"]):
        return "You're welcome! Anything else I can help you with?"
    elif any(keyword in user_input_lower for keyword in ["goodbye", "bye", "अलविदा", "विदाई"]):
        return "Goodbye! Have a great day!"
    else:
        return "I'm sorry, I didn't understand that. Can you please provide more details?"


@app.route('/dynamic_dish_selection', methods=['POST'])
def dynamic_dish_selection():
    user_input = request.json.get('query')
    preference = extract_preference(user_input)
    if preference:
        dishes = fetch_dishes_by_preference(preference)
        return jsonify({"response": dishes})
    else:
        return jsonify({"response": "I'm sorry, I didn't catch that. Can you please specify your preference?"})

def extract_preference(user_input):
    user_input_lower = user_input.lower()
    if any(keyword in user_input_lower for keyword in ["spicy", "chatpata", "चटपटा"]):
        if "chinese" in user_input_lower or "चाइनीज" in user_input_lower:
            return "chinese spicy"
    elif any(keyword in user_input_lower for keyword in ["sweet", "meetha", "मीठा"]):
        return "sweet"
    elif any(keyword in user_input_lower for keyword in ["south indian", "साउथ इंडियन"]):
        return "south indian"
    elif any(keyword in user_input_lower for keyword in ["italian", "इटालियन"]):
        return "italian"
    else:
        return None

@app.route('/get_restaurant_by_name',methods=['GET'])
def get_restaurant_by_name(name):
    return db.restaurants.find_one({"name": {"$regex": name, "$options": "i"}})

@app.route('/get_menu_for_restaurant',methods=['GET'])
def get_menu_for_restaurant(restaurant_id):
    dishes = db.dishes.find({"restaurant_id": restaurant_id})
    if dishes.count() == 0:
        return "No dishes available for this restaurant."
    return ", ".join([dish["name"] for dish in dishes])

@app.route('/fetch_dishes_by_reference')
def fetch_dishes_by_preference(preference):
    query = {"$or": []}
    if "spicy" in preference:
        query["$or"].append({"tags": {"$regex": "spicy", "$options": "i"}})
    if "sweet" in preference:
        query["$or"].append({"tags": {"$regex": "sweet", "$options": "i"}})
    if "chinese" in preference:
        query["$or"].append({"tags": {"$regex": "chinese", "$options": "i"}})
    if "south indian" in preference:
        query["$or"].append({"tags": {"$regex": "south indian", "$options": "i"}})
    if "italian" in preference:
        query["$or"].append({"tags": {"$regex": "italian", "$options": "i"}})
    
    dishes = db.dishes.find(query)
    dish_list = []
    for dish in dishes:
        dish_data = {
            "name": dish.get("name", "Unknown"),
            "description": dish.get("description", "No description available"),
            "price": dish.get("price", "Price not listed"),
            "portion_size": dish.get("portion_size", "Portion size not listed"),
            "resto_name": dish.get("resto_name", "Restaurant name not listed"),
            "image": dish.get("image", "Image not available")
        }
        dish_list.append(dish_data)
    
    if not dish_list:
        return "No dishes matching your preference found."
    
    return "Here are some dishes matching your preference: " + ", ".join([f"{dish['name']} ({dish['price']}, {dish['portion_size']}, {dish['resto_name']})" for dish in dish_list])

@app.route('/list_restaurants',methods=['GET'])
def list_restaurants():
    restaurants = db.restaurants.find()
    restaurant_list = [resto.get('name', 'Unnamed Restaurant') for resto in restaurants]

    if not restaurant_list:
        return "No restaurants found."

    return "Here are the available restaurants: " + ", ".join(restaurant_list)



@app.route('/confirm_order_query',methods=['POST'])
def confirm_order_query():
    order_id = session.get('order_id')
    if order_id:
        return f"Your current order ID is {order_id}. Would you like to confirm this order?"
    else:
        return "There is no order in progress to confirm."

# Test MongoDB connection
@app.route('/test_db')
def test_db():
    try:
        client.server_info()  # Trigger exception if unable to connect to MongoDB
        return jsonify({"status": "success", "message": "Connected to MongoDB"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/collect_user_preferences', methods=['POST'])
def collect_user_preferences():
    user_data = request.json
    required_fields = ["phone_number", "name", "dob", "email", "address", "food_preferences", "health_conditions", "delivery_tags"]

    # Check if all required fields are provided
    if not all(field in user_data for field in required_fields):
        return jsonify({"status": "error", "message": "Missing required user data"})

    # Insert user data into the database
    db.users.insert_one(user_data)
    return jsonify({"status": "success"})

def generate_recommendations(selected_dishes):
    # Placeholder function for generating recommendations
    # In a real-world scenario, this function would use some algorithm or logic
    # to generate recommendations based on the selected dishes
    recommendations = ["Recommendation 1", "Recommendation 2", "Recommendation 3"]
    return recommendations

def show_recommendations(recommendations):
    if recommendations:
        return "Here are some recommendations: " + ", ".join(recommendations)
    else:
        return "No recommendations available."

@app.route('/get_recommendations', methods=['POST'])
def get_recommendations():
    selected_dishes = request.json.get('selected_dishes')
    recommendations = generate_recommendations(selected_dishes)
    return jsonify({"recommendations": recommendations})

# Example usage:
# Send a POST request to '/get_recommendations' with JSON payload like:
# {
#     "selected_dishes": ["Dish1", "Dish2", "Dish3"]
# }

# Haversine function to calculate the distance between two points
# Function to calculate haversine distance
def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # Earth radius in kilometers
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = math.sin(d_lat/2) * math.sin(d_lat/2) + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon/2) * math.sin(d_lon/2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c


@app.route('/fetch_dishes_sorted_by_distance', methods=['GET'])
def fetch_dishes_sorted_by_distance():
    try:
        lat = float(request.args.get('lat'))
        lng = float(request.args.get('lng'))
        page = int(request.args.get('page', 1))
        per_page = 4

        restaurants = db.restaurants.find()
        dishes_with_distance = []

        for restaurant in restaurants:
            resto_lat = restaurant.get("lat")
            resto_lng = restaurant.get("lng")

            if resto_lat is None or resto_lng is None:
                continue  # Skip this restaurant if lat or lng is None

            distance = haversine(lat, lng, resto_lat, resto_lng)

            for dish in restaurant.get('menu', []):
                dish_info = {
                    "name": dish.get('name'),
                    "price": dish.get('price'),
                    "portion_size": dish.get('portion_size'),
                    "tags": dish.get('tags'),
                    "image": dish.get('image'),
                    "resto_name": restaurant.get('name'),
                    "distance": distance
                }
                dishes_with_distance.append(dish_info)

        sorted_dishes = sorted(dishes_with_distance, key=lambda x: x['distance'])

        # Paginate results
        start = (page - 1) * per_page
        end = start + per_page
        paginated_dishes = sorted_dishes[start:end]

        return jsonify({
            "dishes": paginated_dishes,
            "total_dishes": len(sorted_dishes),
            "page": page,
            "per_page": per_page
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    

@app.route('/view_more_dishes', methods=['GET'])
def view_more_dishes():
    lat = request.args.get('lat')
    lng = request.args.get('lng')
    page = request.args.get('page', 1)

    # Fetch next set of dishes
    response = fetch_dishes_sorted_by_distance(lat=lat, lng=lng, page=page)
    return response

@app.route('/display_dishes', methods=['GET'])
def display_dishes():
    dishes = list(db.dishes.find())  # Fetch all dishes from MongoDB

    # Render dishes.html template with fetched dishes
    return render_template('dishes.html', dishes=dishes)

@app.route('/initiate_payment', methods=['POST'])
def initiate_payment():
    try:
        # Simulate payment initiation
        order_data = request.json
        amount = order_data.get('amount')
        user_id = order_data.get('user_id')
        
        if not amount or not user_id:
            return jsonify({"status": "error", "message": "Invalid payment data"})
        
        # Generate a dummy payment ID
        payment_id = f"PAY{random.randint(1000, 9999)}"
        
        # Store payment details in session for simulation purposes
        session['payment_id'] = payment_id
        session['amount'] = amount
        
        # Generate a QR code for the simulated payment
        payment_url = f"http://127.0.0.1:5000/simulate_payment_status?payment_id={payment_id}&status=success"
        qr = qrcode.make(payment_url)
        qr_path = os.path.join(os.getcwd(), "static/payment_qr.png")
        qr.save(qr_path)
        
        return jsonify({"status": "success", "qr_code_path": qr_path, "payment_id": payment_id})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route('/simulate_payment_status', methods=['GET'])
def simulate_payment_status():
    try:
        payment_id = request.args.get('payment_id')
        status = request.args.get('status')
        
        if payment_id != session.get('payment_id'):
            return jsonify({"status": "error", "message": "Invalid payment ID"})
        
        if status == "success":
            # Update order status to 'confirmed' (simulation)
            return jsonify({"status": "success", "message": "Payment successful"})
        else:
            # Update order status to 'failed' (simulation)
            return jsonify({"status": "error", "message": "Payment failed"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/test_payment', methods=['GET'])
def test_payment():
    return render_template('test_payment.html')

@app.route('/dashboard')
def dashboard():
    users = list(db.users.find())
    orders = list(db.orders.find())
    restaurants = list(db.restaurants.find())
    
    return render_template('dashboard.html', users=users, orders=orders, restaurants=restaurants)

def finalize_order():
    order_data = request.get_json()
      # Example processing logic
    order_id = order_data.get('order_id')
    user_id = order_data.get('user_id')
    payment_method = order_data.get('payment_method')
    total_amount = order_data.get('total_amount')

    response = {
        'message': f'Order {order_id} finalized successfully',
        'payment_method': payment_method,
        'total_amount': total_amount
        }

    # Here you would process the order_data to finalize the order
    # Example logic: save the order to database, send confirmation email, etc.
    
    # For now, let's assume you simply return a success message
    return jsonify(response)


if __name__ == "__main__":
    app.run(debug=True)
    # Example inputs to test the new logic
    #test_inputs = [
    """"
        "I want Kuch spicy in Chinese jo heavy na ho",
        "Can I have something sweet?",
        "What do you have in Chinese?",
        "Show me the menu",
        "restaurants",
        "Hello",
        "मुझे मीठा कुछ चाहिए।",
        "चाइनीज में क्या है?",
        "मेनू दिखाओ।",
        "नमस्ते!",
        "I want चाइनीज food with some मसाला.",
        "मुझे something sweet चाहिए.",
        "Show me the menu for Chinese restaurants.",
        "restaurants कहाँ हैं?"
    #]
    """

"""
    # Test the responses
    for test_input in test_inputs:
        print(f"User input: {test_input}")
        response = simulate_llm_response(test_input)
        print(f"Response: {response}\n")
"""



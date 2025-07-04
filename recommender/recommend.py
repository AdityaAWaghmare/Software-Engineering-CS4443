from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import normalize
from scipy.spatial.distance import cdist
from sklearn.cluster import KMeans
import numpy as np
import write_db
import read_db
import os


def recommend_friends(connection_pool, user_id):
    '''
    Input: user
    Output: status code indicating success or failure
    '''

    current_user_data, other_users_data = read_db.get_never_recommended_users_from_db(connection_pool, user_id)
    if not current_user_data or not other_users_data:
        return 204  # No content to recommend

    current_user_array = np.array([[i]+lst for (i, lst) in current_user_data], dtype=np.float32)
    users_data_array = np.array([[i]+lst for (i, lst) in other_users_data], dtype=np.float32)

    # Compute cosine similarity between the current user and all other users
    similarities = cosine_similarity(current_user_array[:, 1:], users_data_array[:, 1:])[0]

    # Get the top N users based on similarity scores
    N = int(os.getenv("MAX_FRIENDS_RECOMMENDATIONS", 5))  # You can adjust this value as needed
    top_indices = np.argsort(similarities)[-N:][::-1]  # Get the indices of the top N similar users

    # Extract the user IDs of the top N similar users and ensure they are integers
    recommended_users = users_data_array[top_indices, 0].astype(np.int32).flatten().tolist()
    similarity_scores = similarities[top_indices].tolist()

    # Zip recommended users with their similarity scores
    recommended_id_similarity_scores = list(zip(recommended_users, similarity_scores))

    # Send recommendations to the database
    success = write_db.send_friend_recommendations_to_db(connection_pool, user_id, recommended_id_similarity_scores)
    
    return 200 if success else 500


def recommend_groups(connection_pool, user_id):
    '''
    Input: user
    Output: status code indicating success or failure
    '''

    current_user_data, group_data = read_db.get_never_recommended_groups_from_db(connection_pool, user_id)
    if not current_user_data or not group_data:
        return 204  # No content to recommend

    current_user_array = np.array([[i] + lst for (i, lst) in current_user_data], dtype=np.float32)
    group_data_array = np.array([[i] + lst for (i, lst) in group_data], dtype=np.float32)

    # Compute cosine similarity between the current user and all other groups
    similarities = cosine_similarity(current_user_array[:, 1:], group_data_array[:, 1:])[0]

    # Get the top N groups based on similarity scores
    N = int(os.getenv("MAX_GROUPS_RECOMMENDATIONS", 1))  # You can adjust this value as needed
    top_indices = np.argsort(similarities)[-N:][::-1]  # Get the indices of the top N similar groups

    # Extract the group IDs of the top N similar groups
    recommended_groups = group_data_array[top_indices, 0].astype(np.int32).flatten().tolist()
    similarity_scores = similarities[top_indices].tolist()

    # Zip recommended groups with their similarity scores
    recommended_group_id_similarity_scores = list(zip(recommended_groups, similarity_scores))

    # Send recommendations to the database
    success = write_db.send_group_recommendations_to_db(connection_pool, user_id, recommended_group_id_similarity_scores)

    return 200 if success else 500


def create_new_group(connection_pool, group_name):
    '''
    Input: None
    Output: list of new groups to be created
    '''

    users_data = read_db.get_all_users_from_db(connection_pool)
    groups_data = read_db.get_all_groups_from_db(connection_pool)
    if not users_data:
        return 500

    users_data_array = np.array([[i] + lst for (i, lst) in users_data], dtype=np.float32)

    # Normalize user feature vectors (excluding ID column) for closer approximation of cosine through euclidean k means
    users_data_array[:, 1:] = normalize(users_data_array[:, 1:], norm='l2', axis=1)

    n_clusters = min(users_data_array.shape[0] // 10 + 1, int(os.getenv("MAX_CLUSTERS", 100)))
    
    # Perform k-means clustering on users_data
    kmeans = KMeans(n_clusters=n_clusters, random_state=42)
    kmeans.fit(users_data_array[:, 1:])  # Exclude the user_id column for clustering

    # Get the cluster centers
    cluster_centers = kmeans.cluster_centers_

    if not groups_data:
        # If there are no existing groups, create a new group with the first cluster center
        hobby_rating_list = cluster_centers[0].tolist()
        success = write_db.insert_new_group(connection_pool, group_name, hobby_rating_list)
        return 200 if success else 500
    
    groups_data_array = np.array([[i] + lst for (i, lst) in groups_data], dtype=np.float32)
    # Compute similarities between cluster centers and existing groups
    similarities = cosine_similarity(cluster_centers, groups_data_array[:, 1:])

    # Find the cluster most de-similar from all existing groups
    farthest_cluster_index = np.argmin(np.max(similarities, axis=1))
    farthest_cluster_center = cluster_centers[farthest_cluster_index]

    # Insert the farthest cluster center as a new group into the database
    hobby_rating_list = farthest_cluster_center.tolist()

    success = write_db.insert_new_group(connection_pool, group_name, hobby_rating_list)
    return 200 if success else 500
import numpy as np
import math
import cv2
from scipy.ndimage import map_coordinates

pad_height = 0

def find_leftmost_pixel(binary_image):
    # Find all pixel coordinates with a value of 255
    white_pixel_coords = np.argwhere(binary_image == 255)

    # Sort pixel coordinates by their x values (column index)
    sorted_coords = white_pixel_coords[np.argsort(white_pixel_coords[:, 1])]

    # Return the first element (leftmost) in the sorted list
    leftmost_pixel = sorted_coords[0]
    
    return leftmost_pixel[::-1]

def distance(x1, y1, x2, y2):
    return math.sqrt((x2 - x1)**2 + (y2 - y1)**2)

def y_distance(y1, y2):
    return abs(y2 - y1)

def x_coord_on_line(line, y):
    rho, theta = line
    a = np.cos(theta)
    b = np.sin(theta)
    x0 = a * rho
    y0 = b * rho

    if np.isclose(np.sin(theta), 0):
        return None  # The line is horizontal, so there's no unique x-coordinate for the given y-coordinate

    x = (rho - y * b) / a
    return x

def line_intersection(line1, line2):
    rho1, theta1 = line1
    rho2, theta2 = line2
    A = np.array([
        [np.cos(theta1), np.sin(theta1)],
        [np.cos(theta2), np.sin(theta2)]
    ])
    b = np.array([rho1, rho2])
    x0, y0 = np.linalg.solve(A, b)
    x0, y0 = int(np.round(x0)), int(np.round(y0))
    return (x0, y0)

def angle_between_lines(line1, line2):
    _, theta1 = line1
    _, theta2 = line2

    # Calculate the absolute difference between the two angles
    angle_diff = abs(theta1 - theta2)

    # If the angle difference is greater than 180 degrees (pi radians), subtract it from 360 degrees (2*pi radians)
    if angle_diff > np.pi:
        angle_diff = 2 * np.pi - angle_diff

    # Return the inner angle by subtracting the outer angle from 180 degrees (pi radians)
    inner_angle = np.pi - angle_diff

    return inner_angle

def find_linear_fov(binary_image, threshold=100):
    
    point_bottom_left = find_leftmost_pixel(binary_image)
    
    # Apply Canny edge detection
    edges = cv2.Canny(binary_image, 100, 200)
    #mmcv.imshow(edges)
    
    # Apply Hough Line Transform to find the lines corresponding to the FOV
    lines = cv2.HoughLines(edges, rho=1, theta=np.pi / 180, threshold=threshold)
    
    # Create a blank image with the same dimensions as the original image
    line_image = np.copy(binary_image)
    
    if lines is not None:
        # Filter and process lines to find left and right edges of the FOV
        left_edge, right_edge = None, None

        for line in lines:
            for rho, theta in line:
                # Filter lines based on the angle (e.g., vertical lines)
                if 20 * np.pi / 180 < theta < 90 * np.pi / 180:
                    if left_edge is None or rho < left_edge[0]:
                        left_edge = (rho, theta)
                        a = np.cos(theta)
                        b = np.sin(theta)
                        x0 = a * rho
                        y0 = b * rho
                        x1 = int(x0 + 1000 * (-b))
                        y1 = int(y0 + 1000 * (a))
                        x2 = int(x0 - 1000 * (-b))
                        y2 = int(y0 - 1000 * (a))
                        cv2.line(line_image, (x1, y1), (x2, y2), (255), 2)
                elif 91 * np.pi / 180 < theta < 160 * np.pi / 180:
                    if right_edge is None or rho > right_edge[0]:
                        right_edge = (rho, theta)
                        a = np.cos(theta)
                        b = np.sin(theta)
                        x0 = a * rho
                        y0 = b * rho
                        x1 = int(x0 + 1000 * (-b))
                        y1 = int(y0 + 1000 * (a))
                        x2 = int(x0 - 1000 * (-b))
                        y2 = int(y0 - 1000 * (a))
                        cv2.line(line_image, (x1, y1), (x2, y2), (255), 2)

        if left_edge and right_edge:
            #print(left_edge, right_edge)
            transducer_point = line_intersection(left_edge, right_edge)
            #print(transducer_point[0], transducer_point[1])
            width = abs(right_edge[0] - left_edge[0])
            
            x_fow_top_left = x_coord_on_line(left_edge, pad_height)
            cv2.circle(line_image, (int(x_fow_top_left), int(pad_height)), 10, (128), -1)
            
            # Draw xoffset, yoffset, and width on the image
            #cv2.line(line_image, (int(xoffset - width / 2), int(binary_image.shape[1] // 2)), 
            #         (int(xoffset + width / 2), int(binary_image.shape[1] // 2)), 
            #         (128), 2)
            cv2.circle(line_image, (int(transducer_point[0]), int(transducer_point[1])), 10, (128), -1)
            
            cv2.circle(line_image, point_bottom_left, 10, (128), -1)
            
            # ray length in FOV
            dc = distance(*point_bottom_left, x_fow_top_left, pad_height)
            cv2.line(line_image, point_bottom_left, 
                     (int(x_fow_top_left), pad_height), (128), 2)
            
            transducer_radius = distance(*transducer_point, x_fow_top_left, pad_height)
            
            y_offset = y_distance(transducer_point[1], pad_height)
            cv2.line(line_image, transducer_point, 
                     (transducer_point[0], transducer_point[1]+y_offset), (128), 2)
            
            x_offset = transducer_point[0]
            cv2.line(line_image, (0, transducer_point[1]+y_offset), 
                     (transducer_point[0], transducer_point[1]+y_offset), (128), 2)

            return x_offset, y_offset, transducer_radius, angle_between_lines(left_edge, right_edge), dc
    return None

def coord_transform(i, j, rc, theta_c, delta_r, delta_theta, xoffset, yoffset):
    x = (rc + i * delta_r) * np.cos(-theta_c / 2 + j * delta_theta) + xoffset
    y = (rc + i * delta_r) * np.sin(-theta_c / 2 + j * delta_theta) + yoffset

    return x, y

def inverse_transform(x, y, rc, theta_c, delta_r, delta_theta, xoffset, yoffset):

    j = (np.sqrt((x - xoffset)**2 + (y - yoffset)**2) - rc) / delta_r
    i = (np.arctan2(y - yoffset, x - xoffset) + (theta_c / 2)) / delta_theta

    return i, j


def bilinear_interpolation(image, x, y):
    x1, y1 = int(x), int(y)
    x2, y2 = x1 + 1, y1 + 1

    # Check if interpolation coordinates are within the image bounds
    if 0 <= x1 < image.shape[1] and 0 <= x2 < image.shape[1] and 0 <= y1 < image.shape[0] and 0 <= y2 < image.shape[0]:
        Q11 = image[y1, x1]
        Q21 = image[y1, x2]
        Q12 = image[y2, x1]
        Q22 = image[y2, x2]

        R1 = ((x2 - x) / (x2 - x1)) * Q11 + ((x - x1) / (x2 - x1)) * Q21
        R2 = ((x2 - x) / (x2 - x1)) * Q12 + ((x - x1) / (x2 - x1)) * Q22

        P = ((y2 - y) / (y2 - y1)) * R1 + ((y - y1) / (y2 - y1)) * R2

        return P.astype(np.uint8)
    else:
        return np.zeros(3, dtype=np.uint8)  # Return black pixel if coordinates are outside the image bounds

def pre_dsc_image(IUSI, dc, rc, theta_c, xoffset, yoffset, width, height):
    delta_r = dc / height
    delta_theta = theta_c / width
    IRSC = np.zeros((height, width, 3), dtype=np.uint8)

    for i in range(height):
        for j in range(width):
            x, y = coord_transform(i, j, rc, theta_c, delta_r, delta_theta, -xoffset, yoffset)

            if 0 <= y < IUSI.shape[1] and 0 <= x < IUSI.shape[0]:
                IRSC[i, j] = bilinear_interpolation(IUSI, y, x)

    return IRSC


def pre_dsc_image_vectorized(IUSI, dc, rc, theta_c, xoffset, yoffset, width, height, get_IUSI_FOV=False):
    delta_r = dc / height
    delta_theta = theta_c / width

    i_range, j_range = np.meshgrid(np.arange(height), np.arange(width), indexing='ij')

    x, y = coord_transform(i_range, j_range, rc, theta_c, delta_r, delta_theta, -xoffset, yoffset)
    
    coords = np.array([x, y])
    
    IRSC = map_coordinates(IUSI, coords, order=1, mode='nearest', prefilter=False)

    if get_IUSI_FOV:
        # Create a binary mask with the same shape as IUSI
        mask = np.zeros_like(IUSI, dtype=np.uint8)

        # Calculate valid indices within the IUSI shape
        valid_indices = np.logical_and(np.logical_and(0 <= coords[0], coords[0] < IUSI.shape[0]),
                                       np.logical_and(0 <= coords[1], coords[1] < IUSI.shape[1]))

        # Round coordinates and ensure they are within the bounds of the IUSI shape
        valid_x = np.clip(np.round(coords[0][valid_indices]).astype(int), 0, IUSI.shape[0] - 1)
        valid_y = np.clip(np.round(coords[1][valid_indices]).astype(int), 0, IUSI.shape[1] - 1)

        # Set valid coordinates in the mask to 255
        mask[valid_x, valid_y] = 255
        
        # Fill the holes in the mask using dilation
        kernel = np.ones((3, 3), dtype=np.uint8)
        filled_mask = cv2.dilate(mask, kernel, iterations=1)

        return filled_mask

    return IRSC


def dsc_image_vectorized(IRSC, dc, rc, theta_c, xoffset, yoffset, height, width, backscan_width, backscan_height):
    delta_r = dc / backscan_height
    delta_theta = theta_c / backscan_width

    x_range, y_range = np.meshgrid(np.arange(width), np.arange(height), indexing='ij')

    j, i = inverse_transform(x_range, y_range, rc, theta_c, delta_r, delta_theta, -xoffset, yoffset)
    
    coords = np.array([i, j])
    
    IUSI = map_coordinates(IRSC, coords, order=1, mode='constant', prefilter=False)

    return IUSI
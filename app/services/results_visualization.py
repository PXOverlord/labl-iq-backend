import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import json
from typing import Dict, List, Any, Tuple, Optional
import logging

def zone_analysis(results: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Generate zone analysis visualization and summary data
    
    Args:
        results: List of shipment result dictionaries
        
    Returns:
        Tuple containing:
        - JSON string of Plotly figure for zone distribution and savings
        - List of dictionaries with zone summary data for tabular display
    """
    # Convert results to DataFrame for easier analysis
    df = pd.DataFrame(results)
    
    # Skip if no zone data
    if 'zone' not in df.columns or df['zone'].isna().all():
        return None, []
    
    # Group by zone
    zone_summary = df.groupby('zone', observed=False).agg({
        'package_id': 'count',
        'amazon_rate': 'mean',
        'current_rate': 'mean',
        'savings': 'sum',
        'savings_percent': 'mean'
    }).reset_index()
    
    # Rename columns for clarity
    zone_summary.columns = ['Zone', 'Shipments', 'Avg Amazon Rate', 'Avg Current Rate', 'Total Savings', 'Avg Savings %']
    
    # Round numeric columns
    for col in zone_summary.columns[1:]:
        zone_summary[col] = zone_summary[col].round(2)
    
    # Create zone distribution figure
    fig = go.Figure()
    
    # Add shipment count bars
    fig.add_trace(go.Bar(
        x=zone_summary['Zone'],
        y=zone_summary['Shipments'],
        name='Shipment Count',
        marker_color='#4C78A8'
    ))
    
    # Add savings line on secondary y-axis
    fig.add_trace(go.Scatter(
        x=zone_summary['Zone'],
        y=zone_summary['Avg Savings %'],
        name='Avg Savings %',
        mode='lines+markers',
        marker=dict(color='#72B7B2'),
        line=dict(width=3),
        yaxis='y2'
    ))
    
    # Update layout with dual y-axis
    fig.update_layout(
        title='Zone Analysis: Distribution and Savings',
        xaxis=dict(title='Zone'),
        yaxis=dict(title='Shipment Count'),
        yaxis2=dict(
            title='Avg Savings %',
            overlaying='y',
            side='right',
            ticksuffix='%'
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        height=500,
        margin=dict(l=50, r=50, t=80, b=50)
    )
    
    # Convert figure to JSON for frontend rendering
    fig_json = fig.to_json()
    
    # Return the figure JSON and summary data for table
    return fig_json, zone_summary.to_dict('records')

def weight_analysis(results: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Generate weight analysis visualization and summary data
    
    Args:
        results: List of shipment result dictionaries
        
    Returns:
        Tuple containing:
        - JSON string of Plotly figure for weight distribution and savings
        - List of dictionaries with weight summary data for tabular display
    """
    # Convert results to DataFrame for easier analysis
    df = pd.DataFrame(results)
    
    # Skip if no weight data
    if 'weight' not in df.columns or df['weight'].isna().all():
        return None, []
    
    # Create weight brackets
    weight_bins = [0, 1, 5, 10, 20, 50, 100, float('inf')]
    weight_labels = ['0-1 lbs', '1-5 lbs', '5-10 lbs', '10-20 lbs', '20-50 lbs', '50-100 lbs', '100+ lbs']
    
    # Use billable_weight if available, otherwise use weight
    weight_col = 'billable_weight' if 'billable_weight' in df.columns else 'weight'
    df['weight_bracket'] = pd.cut(df[weight_col], bins=weight_bins, labels=weight_labels)
    
    # Group by weight bracket
    weight_summary = df.groupby('weight_bracket', observed=False).agg({
        'package_id': 'count',
        'amazon_rate': 'mean',
        'current_rate': 'mean',
        'savings': 'sum',
        'savings_percent': 'mean'
    }).reset_index()
    
    # Rename columns for clarity
    weight_summary.columns = ['Weight Range', 'Shipments', 'Avg Amazon Rate', 'Avg Current Rate', 'Total Savings', 'Avg Savings %']
    
    # Round numeric columns
    for col in weight_summary.columns[1:]:
        weight_summary[col] = weight_summary[col].round(2)
    
    # Create weight distribution figure
    fig = go.Figure()
    
    # Add shipment count bars
    fig.add_trace(go.Bar(
        x=weight_summary['Weight Range'],
        y=weight_summary['Shipments'],
        name='Shipment Count',
        marker_color='#E45756'
    ))
    
    # Add savings line on secondary y-axis
    fig.add_trace(go.Scatter(
        x=weight_summary['Weight Range'],
        y=weight_summary['Avg Savings %'],
        name='Avg Savings %',
        mode='lines+markers',
        marker=dict(color='#54A24B'),
        line=dict(width=3),
        yaxis='y2'
    ))
    
    # Update layout with dual y-axis
    fig.update_layout(
        title='Weight Analysis: Distribution and Savings',
        xaxis=dict(title='Weight Range'),
        yaxis=dict(title='Shipment Count'),
        yaxis2=dict(
            title='Avg Savings %',
            overlaying='y',
            side='right',
            ticksuffix='%'
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        height=500,
        margin=dict(l=50, r=50, t=80, b=50)
    )
    
    # Convert figure to JSON for frontend rendering
    fig_json = fig.to_json()
    
    # Return the figure JSON and summary data for table
    return fig_json, weight_summary.to_dict('records')

def surcharge_analysis(results: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Generate surcharge analysis visualization and summary data
    
    Args:
        results: List of shipment result dictionaries
        
    Returns:
        Tuple containing:
        - JSON string of Plotly figure for surcharge frequency and impact
        - List of dictionaries with surcharge summary data for tabular display
    """
    # Convert results to DataFrame for easier analysis
    df = pd.DataFrame(results)
    
    # Define surcharge columns to analyze
    surcharge_cols = ['das_surcharge', 'edas_surcharge', 'remote_surcharge', 'fuel_surcharge']
    display_names = ['DAS', 'EDAS', 'Remote', 'Fuel']
    
    # Skip if no surcharge data
    if not any(col in df.columns for col in surcharge_cols):
        return None, []
    
    # Prepare data for surcharge summary
    surcharge_data = []
    
    for col, name in zip(surcharge_cols, display_names):
        if col in df.columns:
            # Calculate metrics
            frequency = (df[col] > 0).mean() * 100
            total_amount = df[col].sum()
            avg_amount = df[col].mean()
            max_amount = df[col].max()
            
            surcharge_data.append({
                'Surcharge': name,
                'Frequency (%)': round(frequency, 2),
                'Total Amount': round(total_amount, 2),
                'Avg Amount': round(avg_amount, 2),
                'Max Amount': round(max_amount, 2)
            })
    
    # Create surcharge analysis figure
    fig = go.Figure()
    
    # Extract data for plotting
    surcharge_names = [item['Surcharge'] for item in surcharge_data]
    frequencies = [item['Frequency (%)'] for item in surcharge_data]
    total_amounts = [item['Total Amount'] for item in surcharge_data]
    
    # Add frequency bars
    fig.add_trace(go.Bar(
        x=surcharge_names,
        y=frequencies,
        name='Frequency (%)',
        marker_color='#F58518',
        text=frequencies,
        texttemplate='%{text:.1f}%',
        textposition='outside'
    ))
    
    # Add total amount line on secondary y-axis
    fig.add_trace(go.Bar(
        x=surcharge_names,
        y=total_amounts,
        name='Total Amount ($)',
        marker_color='#9D755D',
        text=total_amounts,
        texttemplate='$%{text:.2f}',
        textposition='outside',
        yaxis='y2'
    ))
    
    # Update layout with dual y-axis
    fig.update_layout(
        title='Surcharge Analysis: Frequency and Impact',
        xaxis=dict(title='Surcharge Type'),
        yaxis=dict(
            title='Frequency (%)',
            ticksuffix='%'
        ),
        yaxis2=dict(
            title='Total Amount ($)',
            overlaying='y',
            side='right',
            tickprefix='$'
        ),
        barmode='group',
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        height=500,
        margin=dict(l=50, r=50, t=80, b=50)
    )
    
    # Convert figure to JSON for frontend rendering
    fig_json = fig.to_json()
    
    # Return the figure JSON and summary data for table
    return fig_json, surcharge_data

def generate_all_visualizations(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Generate all visualizations for the results page
    
    Args:
        results: List of shipment result dictionaries
        
    Returns:
        Dictionary containing all visualization data and figures
    """
    # Initialize visualization data dictionary
    visualizations = {}
    
    # Skip visualizations if error message exists
    if results and results[0].get('error_message'):
        return {}
        
    try:
        # 1. Generate zone analysis
        zone_fig_json, zone_table = zone_analysis(results)
        visualizations['zone_fig'] = zone_fig_json
        visualizations['zone_table'] = zone_table
        
        # 2. Generate weight analysis
        weight_fig_json, weight_table = weight_analysis(results)
        visualizations['weight_fig'] = weight_fig_json
        visualizations['weight_table'] = weight_table
        
        # 3. Generate surcharge analysis
        surcharge_fig_json, surcharge_table = surcharge_analysis(results)
        visualizations['surcharge_fig'] = surcharge_fig_json
        visualizations['surcharge_table'] = surcharge_table
    except Exception as e:
        # Log error but don't crash
        logger = logging.getLogger('labl_iq.visualization')
        logger.error(f"Error generating visualizations: {str(e)}", exc_info=True)
    
    return visualizations

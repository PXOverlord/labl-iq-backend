import pandas as pd
import io
from typing import Dict, List, Any, Tuple, Optional, BinaryIO
from fastapi.responses import StreamingResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('labl_iq.download')

def to_csv(results: List[Dict[str, Any]], filename: str = "labl_iq_results.csv") -> Tuple[BinaryIO, str, str]:
    """
    Convert results to CSV format
    
    Args:
        results: List of result dictionaries
        filename: Name of the file to be downloaded
        
    Returns:
        Tuple containing:
        - BytesIO object with CSV data
        - MIME type
        - Filename
    """
    try:
        # Convert results to DataFrame
        df = pd.DataFrame(results)
        
        # Create a BytesIO object to store the CSV data
        output = io.BytesIO()
        
        # Write DataFrame to CSV
        df.to_csv(output, index=False)
        
        # Reset the pointer to the beginning of the BytesIO object
        output.seek(0)
        
        return output, "text/csv", filename
    except Exception as e:
        logger.error(f"Error generating CSV: {str(e)}")
        # Return an empty CSV with error message
        output = io.BytesIO(b"Error generating CSV file")
        output.seek(0)
        return output, "text/csv", filename

def to_excel(results: List[Dict[str, Any]], filename: str = "labl_iq_results.xlsx") -> Tuple[BinaryIO, str, str]:
    """
    Convert results to Excel format with multiple sheets for different analyses
    
    Args:
        results: List of result dictionaries
        filename: Name of the file to be downloaded
        
    Returns:
        Tuple containing:
        - BytesIO object with Excel data
        - MIME type
        - Filename
    """
    try:
        # Convert results to DataFrame
        df = pd.DataFrame(results)
        
        # Create a BytesIO object to store the Excel data
        output = io.BytesIO()
        
        # Create Excel writer
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Write main results to the first sheet
            df.to_excel(writer, sheet_name='Results', index=False)
            
            # Create zone analysis sheet if zone data is available
            if 'zone' in df.columns:
                zone_summary = df.groupby('zone').agg({
                    'package_id': 'count',
                    'amazon_rate': ['mean', 'sum'],
                    'current_rate': ['mean', 'sum'],
                    'base_rate': ['mean', 'sum'],
                    'total_surcharges': ['mean', 'sum'],
                    'fuel_surcharge': ['mean', 'sum'],
                    'das_surcharge': ['mean', 'sum'],
                    'edas_surcharge': ['mean', 'sum'],
                    'remote_surcharge': ['mean', 'sum'],
                    'markup_amount': ['mean', 'sum'],
                    'savings': ['mean', 'sum'],
                    'savings_percent': 'mean'
                })
                
                # Flatten the multi-level columns
                zone_summary.columns = [f"{col[0]}_{col[1]}" if col[1] else col[0] for col in zone_summary.columns]
                
                # Rename columns for clarity
                zone_summary = zone_summary.rename(columns={
                    'package_id_count': 'Shipments',
                    'amazon_rate_mean': 'Avg Amazon Rate',
                    'amazon_rate_sum': 'Total Amazon Rate',
                    'current_rate_mean': 'Avg Current Rate',
                    'current_rate_sum': 'Total Current Rate',
                    'base_rate_mean': 'Avg Base Rate',
                    'base_rate_sum': 'Total Base Rate',
                    'total_surcharges_mean': 'Avg Total Surcharges',
                    'total_surcharges_sum': 'Total Surcharges',
                    'fuel_surcharge_mean': 'Avg Fuel Surcharge',
                    'fuel_surcharge_sum': 'Total Fuel Surcharge',
                    'das_surcharge_mean': 'Avg DAS Surcharge',
                    'das_surcharge_sum': 'Total DAS Surcharge',
                    'edas_surcharge_mean': 'Avg EDAS Surcharge',
                    'edas_surcharge_sum': 'Total EDAS Surcharge',
                    'remote_surcharge_mean': 'Avg Remote Surcharge',
                    'remote_surcharge_sum': 'Total Remote Surcharge',
                    'markup_amount_mean': 'Avg Markup Amount',
                    'markup_amount_sum': 'Total Markup Amount',
                    'savings_mean': 'Avg Savings',
                    'savings_sum': 'Total Savings',
                    'savings_percent_mean': 'Avg Savings %'
                })
                
                # Write zone analysis to a separate sheet
                zone_summary.to_excel(writer, sheet_name='Zone Analysis')
            
            # Create weight analysis sheet
            # Create weight brackets
            weight_bins = [0, 1, 5, 10, 20, 50, 100, float('inf')]
            weight_labels = ['0-1 lbs', '1-5 lbs', '5-10 lbs', '10-20 lbs', '20-50 lbs', '50-100 lbs', '100+ lbs']
            
            # Use billable_weight if available, otherwise use weight
            weight_col = 'billable_weight' if 'billable_weight' in df.columns else 'weight'
            if weight_col in df.columns:
                df['weight_bracket'] = pd.cut(df[weight_col], bins=weight_bins, labels=weight_labels)
                
                weight_summary = df.groupby('weight_bracket').agg({
                    'package_id': 'count',
                    'amazon_rate': ['mean', 'sum'],
                    'current_rate': ['mean', 'sum'],
                    'base_rate': ['mean', 'sum'],
                    'total_surcharges': ['mean', 'sum'],
                    'fuel_surcharge': ['mean', 'sum'],
                    'das_surcharge': ['mean', 'sum'],
                    'edas_surcharge': ['mean', 'sum'],
                    'remote_surcharge': ['mean', 'sum'],
                    'markup_amount': ['mean', 'sum'],
                    'savings': ['mean', 'sum'],
                    'savings_percent': 'mean'
                })
                
                # Flatten the multi-level columns
                weight_summary.columns = [f"{col[0]}_{col[1]}" if col[1] else col[0] for col in weight_summary.columns]
                
                # Rename columns for clarity
                weight_summary = weight_summary.rename(columns={
                    'package_id_count': 'Shipments',
                    'amazon_rate_mean': 'Avg Amazon Rate',
                    'amazon_rate_sum': 'Total Amazon Rate',
                    'current_rate_mean': 'Avg Current Rate',
                    'current_rate_sum': 'Total Current Rate',
                    'base_rate_mean': 'Avg Base Rate',
                    'base_rate_sum': 'Total Base Rate',
                    'total_surcharges_mean': 'Avg Total Surcharges',
                    'total_surcharges_sum': 'Total Surcharges',
                    'fuel_surcharge_mean': 'Avg Fuel Surcharge',
                    'fuel_surcharge_sum': 'Total Fuel Surcharge',
                    'das_surcharge_mean': 'Avg DAS Surcharge',
                    'das_surcharge_sum': 'Total DAS Surcharge',
                    'edas_surcharge_mean': 'Avg EDAS Surcharge',
                    'edas_surcharge_sum': 'Total EDAS Surcharge',
                    'remote_surcharge_mean': 'Avg Remote Surcharge',
                    'remote_surcharge_sum': 'Total Remote Surcharge',
                    'markup_amount_mean': 'Avg Markup Amount',
                    'markup_amount_sum': 'Total Markup Amount',
                    'savings_mean': 'Avg Savings',
                    'savings_sum': 'Total Savings',
                    'savings_percent_mean': 'Avg Savings %'
                })
                
                # Write weight analysis to a separate sheet
                weight_summary.to_excel(writer, sheet_name='Weight Analysis')
            
            # Create surcharge analysis sheet
            surcharge_cols = ['das_surcharge', 'edas_surcharge', 'remote_surcharge', 'fuel_surcharge', 'markup_amount']
            if any(col in df.columns for col in surcharge_cols):
                # Create a summary DataFrame for surcharges
                surcharge_data = []
                
                for col in surcharge_cols:
                    if col in df.columns:
                        display_name = col
                        if col == 'markup_amount':
                            display_name = 'MARKUP'
                        else:
                            display_name = col.replace('_surcharge', '').upper()
                            
                        surcharge_data.append({
                            'Surcharge': display_name,
                            'Frequency (%)': (df[col] > 0).mean() * 100,
                            'Total Amount': df[col].sum(),
                            'Avg Amount': df[col].mean(),
                            'Max Amount': df[col].max()
                        })
                
                surcharge_df = pd.DataFrame(surcharge_data)
                surcharge_df.to_excel(writer, sheet_name='Surcharge Analysis', index=False)
                
            # Create a dedicated markup analysis sheet if markup data is available
            if 'markup_percentage' in df.columns and 'markup_amount' in df.columns:
                markup_summary = df.groupby('markup_percentage').agg({
                    'package_id': 'count',
                    'markup_amount': ['mean', 'sum'],
                    'amazon_rate': ['mean', 'sum']
                })
                
                # Flatten the multi-level columns
                markup_summary.columns = [f"{col[0]}_{col[1]}" if col[1] else col[0] for col in markup_summary.columns]
                
                # Rename columns for clarity
                markup_summary = markup_summary.rename(columns={
                    'package_id_count': 'Shipments',
                    'markup_amount_mean': 'Avg Markup Amount',
                    'markup_amount_sum': 'Total Markup Amount',
                    'amazon_rate_mean': 'Avg Total Rate',
                    'amazon_rate_sum': 'Total Rate'
                })
                
                # Write markup analysis to a separate sheet
                markup_summary.to_excel(writer, sheet_name='Markup Analysis')
        
        # Reset the pointer to the beginning of the BytesIO object
        output.seek(0)
        
        return output, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename
    except Exception as e:
        logger.error(f"Error generating Excel: {str(e)}")
        # Return an empty Excel with error message
        output = io.BytesIO()
        df = pd.DataFrame({"Error": [f"Error generating Excel file: {str(e)}"]})
        df.to_excel(output, index=False)
        output.seek(0)
        return output, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename

def to_pdf(results: List[Dict[str, Any]], filename: str = "labl_iq_results.pdf") -> Tuple[BinaryIO, str, str]:
    """
    Convert results to PDF format with tables and summary
    
    Args:
        results: List of result dictionaries
        filename: Name of the file to be downloaded
        
    Returns:
        Tuple containing:
        - BytesIO object with PDF data
        - MIME type
        - Filename
    """
    try:
        # Convert results to DataFrame
        df = pd.DataFrame(results)
        
        # Create a BytesIO object to store the PDF data
        output = io.BytesIO()
        
        # Create the PDF document
        doc = SimpleDocTemplate(output, pagesize=landscape(letter))
        elements = []
        
        # Get styles
        styles = getSampleStyleSheet()
        title_style = styles['Heading1']
        heading_style = styles['Heading2']
        normal_style = styles['Normal']
        
        # Add title
        elements.append(Paragraph("Labl IQ Rate Analysis Results", title_style))
        elements.append(Spacer(1, 12))
        
        # Add summary section
        elements.append(Paragraph("Summary", heading_style))
        elements.append(Spacer(1, 6))
        
        # Calculate summary metrics
        total_packages = len(df)
        total_current_cost = df['current_rate'].sum() if 'current_rate' in df.columns else 0
        total_amazon_cost = df['amazon_rate'].sum() if 'amazon_rate' in df.columns else 0
        total_base_rate = df['base_rate'].sum() if 'base_rate' in df.columns else 0
        total_surcharges = df['total_surcharges'].sum() if 'total_surcharges' in df.columns else 0
        total_markup = df['markup_amount'].sum() if 'markup_amount' in df.columns else 0
        total_savings = df['savings'].sum() if 'savings' in df.columns else 0
        percent_savings = (total_savings / total_current_cost * 100) if total_current_cost > 0 else 0
        
        # Create summary table
        summary_data = [
            ["Metric", "Value"],
            ["Total Packages", str(total_packages)],
            ["Total Current Cost", f"${total_current_cost:.2f}"],
            ["Total Amazon Cost", f"${total_amazon_cost:.2f}"],
            ["Total Base Rate", f"${total_base_rate:.2f}"],
            ["Total Surcharges", f"${total_surcharges:.2f}"],
            ["Total Markup", f"${total_markup:.2f}"],
            ["Total Savings", f"${total_savings:.2f}"],
            ["Percent Savings", f"{percent_savings:.2f}%"]
        ]
        
        summary_table = Table(summary_data, colWidths=[200, 100])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (1, 0), 12),
            ('BACKGROUND', (0, 1), (1, -1), colors.beige),
            ('GRID', (0, 0), (1, -1), 1, colors.black)
        ]))
        
        elements.append(summary_table)
        elements.append(Spacer(1, 12))
        
        # Add results table
        elements.append(Paragraph("Detailed Results", heading_style))
        elements.append(Spacer(1, 6))
        
        # Select columns for the results table (limit to most important)
        columns = [
            'package_id', 'weight', 'zone', 'current_rate', 
            'amazon_rate', 'savings', 'savings_percent'
        ]
        
        # Filter columns that exist in the DataFrame
        columns = [col for col in columns if col in df.columns]
        
        # Create header row with column names
        header_row = [col.replace('_', ' ').title() for col in columns]
        
        # Create data rows (limit to first 100 rows to avoid huge PDFs)
        data_rows = []
        for _, row in df.head(100).iterrows():
            data_row = []
            for col in columns:
                if col in ['current_rate', 'amazon_rate', 'savings']:
                    # Format currency values
                    data_row.append(f"${row[col]:.2f}" if pd.notna(row[col]) else "N/A")
                elif col == 'savings_percent':
                    # Format percentage values
                    data_row.append(f"{row[col]:.2f}%" if pd.notna(row[col]) else "N/A")
                else:
                    # Format other values
                    data_row.append(str(row[col]) if pd.notna(row[col]) else "N/A")
            data_rows.append(data_row)
        
        # Combine header and data rows
        table_data = [header_row] + data_rows
        
        # Create the table
        results_table = Table(table_data)
        
        # Style the table
        table_style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('ALIGN', (1, 1), (-1, -1), 'RIGHT')  # Right-align numeric columns
        ]
        
        # Add alternating row colors
        for i in range(1, len(table_data)):
            if i % 2 == 0:
                table_style.append(('BACKGROUND', (0, i), (-1, i), colors.lightgrey))
        
        results_table.setStyle(TableStyle(table_style))
        
        elements.append(results_table)
        
        # Add note if results were truncated
        if len(df) > 100:
            elements.append(Spacer(1, 12))
            elements.append(Paragraph(f"Note: Only showing first 100 of {len(df)} results.", normal_style))
        
        # Build the PDF
        doc.build(elements)
        
        # Reset the pointer to the beginning of the BytesIO object
        output.seek(0)
        
        return output, "application/pdf", filename
    except Exception as e:
        logger.error(f"Error generating PDF: {str(e)}")
        # Create a simple error PDF
        output = io.BytesIO()
        doc = SimpleDocTemplate(output, pagesize=letter)
        elements = []
        styles = getSampleStyleSheet()
        elements.append(Paragraph("Error generating PDF", styles['Heading1']))
        elements.append(Paragraph(f"Error: {str(e)}", styles['Normal']))
        doc.build(elements)
        output.seek(0)
        return output, "application/pdf", filename

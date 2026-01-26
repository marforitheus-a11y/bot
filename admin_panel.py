# admin_panel.py
import matplotlib
matplotlib.use('Agg') # Importante para rodar sem interface gráfica (VPS)
import matplotlib.pyplot as plt
import io
import db

def generate_sales_graph(days=7):
    """Gera uma imagem (bytes) com o gráfico de vendas."""
    data = db.get_sales_stats(days)
    
    if not data:
        return None
        
    dates = [row[0][5:] for row in data] # Pega só MM-DD
    totals = [row[1] for row in data]    # Total em Dinheiro
    volumes = [row[2] for row in data]   # Quantidade de Vendas
    
    # Cria a figura com 2 eixos (Dinheiro e Volume)
    fig, ax1 = plt.subplots(figsize=(10, 5))
    
    # Barra Azul para Dinheiro ($)
    color = 'tab:blue'
    ax1.set_xlabel('Date (Last 7 Days)')
    ax1.set_ylabel('Revenue ($)', color=color)
    bars = ax1.bar(dates, totals, color=color, alpha=0.6, label='Revenue')
    ax1.tick_params(axis='y', labelcolor=color)
    
    # Adiciona valores em cima das barras
    for bar in bars:
        height = bar.get_height()
        ax1.annotate(f'${height:.0f}',
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3), textcoords="offset points",
                    ha='center', va='bottom')

    # Linha Vermelha para Volume (Qtd)
    ax2 = ax1.twinx()  
    color = 'tab:red'
    ax2.set_ylabel('Sales Volume', color=color)  
    ax2.plot(dates, volumes, color=color, marker='o', linestyle='-', linewidth=2, label='Volume')
    ax2.tick_params(axis='y', labelcolor=color)
    
    plt.title('Sales Performance & Revenue')
    fig.tight_layout()
    
    # Salva na memória
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    
    return buf

# No admin_panel.py

def get_admin_summary():
    """Texto resumido para o painel com Online Users."""
    total_users = db.get_total_users()
    active_now = db.get_active_users_count(minutes=10) # Considera online quem mexeu nos últimos 10 min
    last_sales = db.get_last_sales(5)
    
    report = f"📊 **ADMIN DASHBOARD**\n\n"
    report += f"🟢 **Online Users (10m):** {active_now}\n"
    report += f"👥 **Total Database:** {total_users}\n"
    report += f"-----------------------------\n"
    report += f"📉 **Recent Sales:**\n"
    
    if not last_sales:
        report += "_No sales recorded yet._"
    else:
        for sale in last_sales:
            # User ID, Kit ID, Price, Date
            # Formata a data para ficar curta (HH:MM)
            time_str = sale[3][11:16] 
            report += f"• `${sale[2]:.2f}` - User `{sale[0]}` ({time_str})\n"
            
    return report
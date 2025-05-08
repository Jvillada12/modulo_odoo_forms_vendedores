from odoo import http, fields, _
from odoo.http import request
from odoo.exceptions import AccessError, ValidationError
import werkzeug


class VendorOrderController(http.Controller):
    
    @http.route(['/vendor-orders'], type='http', auth="user", website=True)
    def vendor_order_forms(self, **kw):
        """Vista de todos los formularios de pedidos del vendedor actual"""
        user = request.env.user
        order_forms = request.env['vendor.order.form'].search([('vendor_id', '=', user.id)])
        values = {
            'order_forms': order_forms,
            'page_name': 'vendor_orders',
        }
        return request.render("website_vendor_order_form.vendor_orders_list", values)
    
    @http.route(['/create-vendor-order'], type='http', auth="user", website=True)
    def create_vendor_order(self, **kw):
        """Página para crear un nuevo formulario de pedido"""
        user = request.env.user
        partners = request.env['res.partner'].search([('customer_rank', '>', 0)])
        values = {
            'page_name': 'create_vendor_order',
            'user': user,
            'partners': partners,
        }
        return request.render("website_vendor_order_form.create_vendor_order_form", values)
    
    @http.route(['/vendor-order/<int:order_id>/<string:token>'], type='http', auth="public", website=True)
    def view_vendor_order(self, order_id, token, **kw):
        """Vista pública del formulario de pedido para el cliente"""
        order = request.env['vendor.order.form'].sudo().browse(order_id)
        
        # Verificar el token para acceso público
        if not order.exists() or order.access_token != token:
            return request.render("website_vendor_order_form.404")
        
        # Obtener productos disponibles con stock
        products = request.env['product.product'].sudo().search([
            ('sale_ok', '=', True),
            ('type', '=', 'product'),
            ('qty_available', '>', 0)
        ])
        
        values = {
            'order': order,
            'products': products,
            'page_name': 'vendor_order',
        }
        
        return request.render("website_vendor_order_form.vendor_order_form_public", values)
    
    @http.route(['/vendor-order/submit/<int:order_id>/<string:token>'], type='http', auth="public", methods=['POST'], website=True, csrf=False)
    def submit_vendor_order(self, order_id, token, **post):
        """Procesar el envío del formulario de pedido"""
        order = request.env['vendor.order.form'].sudo().browse(order_id)
        
        # Verificar el token para acceso público
        if not order.exists() or order.access_token != token:
            return request.render("website_vendor_order_form.404")
        
        # Crear o actualizar cliente si se proporcionan datos
        customer_data = {}
        for field in ['name', 'email', 'phone', 'street', 'city']:
            if post.get(f'customer_{field}'):
                customer_data[field] = post.get(f'customer_{field}')
        
        # Datos sociales opcionales
        social_data = {}
        for field in ['facebook', 'instagram', 'whatsapp']:
            if post.get(f'social_{field}'):
                social_data[f'social_{field}'] = post.get(f'social_{field}')
        
        # Crear o actualizar cliente
        if post.get('customer_id'):
            customer = request.env['res.partner'].sudo().browse(int(post.get('customer_id')))
            if customer_data:
                customer.write(customer_data)
        elif customer_data.get('name') and customer_data.get('email'):
            customer = request.env['res.partner'].sudo().create({
                **customer_data,
                'customer_rank': 1,
            })
        else:
            return request.render("website_vendor_order_form.error", {
                'error_message': _("Se requiere al menos nombre y correo electrónico del cliente.")
            })
        
        # Actualizar pedido
        order_data = {
            'customer_id': customer.id,
            'state': 'confirmed',
            **social_data
        }
        
        if post.get('delivery_date'):
            order_data['delivery_date'] = post.get('delivery_date')
        
        if post.get('note'):
            order_data['note'] = post.get('note')
        
        order.write(order_data)
        
        # Procesar líneas de productos
        existing_lines = {line.product_id.id: line for line in order.line_ids}
        
        for key, value in post.items():
            if key.startswith('product_qty_') and float(value) > 0:
                product_id = int(key.split('_')[-1])
                product = request.env['product.product'].sudo().browse(product_id)
                
                if not product.exists() or product.type != 'product' or product.qty_available <= 0:
                    continue
                
                # Limitar la cantidad al stock disponible
                qty = min(float(value), product.qty_available)
                
                if product_id in existing_lines:
                    # Actualizar línea existente
                    existing_lines[product_id].write({
                        'product_qty': qty,
                    })
                else:
                    # Crear nueva línea
                    request.env['vendor.order.form.line'].sudo().create({
                        'order_id': order.id,
                        'product_id': product_id,
                        'product_qty': qty,
                        'price_unit': product.list_price,
                    })
        
        # Crear lead en CRM para seguimiento
        lead_data = {
            'name': f"Pedido de {customer.name}",
            'partner_id': customer.id,
            'user_id': order.vendor_id.id,
            'type': 'opportunity',
            'description': f"Pedido generado desde el formulario web {order.name}",
        }
        crm_lead = request.env['crm.lead'].sudo().create(lead_data)
        
        # Redireccionar a página de confirmación
        return request.render("website_vendor_order_form.confirmation", {
            'order': order,
        })
    
    @http.route(['/vendor-order/save'], type='http', auth="user", methods=['POST'], website=True)
    def save_vendor_order(self, **post):
        """Guardar un nuevo formulario de pedido creado por el vendedor"""
        user = request.env.user
        
        # Validar datos básicos
        if not post.get('partner_id'):
            return werkzeug.utils.redirect('/create-vendor-order?error=missing_partner')
        
        # Crear el formulario
        vals = {
            'vendor_id': user.id,
            'customer_id': int(post.get('partner_id')),
            'delivery_date': post.get('delivery_date') or fields.Date.today(),
            'note': post.get('note', ''),
        }
        
        order_form = request.env['vendor.order.form'].create(vals)
        
        # Redireccionar a la vista pública
        return werkzeug.utils.redirect(f'/vendor-order/{order_form.id}/{order_form.access_token}')

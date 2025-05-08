from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class VendorOrderForm(models.Model):
    _name = 'vendor.order.form'
    _description = 'Formulario de pedido de vendedor'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    
    name = fields.Char(string='Referencia', required=True, copy=False, 
                      readonly=True, default=lambda self: _('Nuevo'))
    vendor_id = fields.Many2one('res.users', string='Vendedor', required=True, 
                              tracking=True, default=lambda self: self.env.user)
    customer_id = fields.Many2one('res.partner', string='Cliente', required=True, tracking=True)
    date_order = fields.Datetime(string='Fecha del pedido', default=fields.Datetime.now, tracking=True)
    delivery_date = fields.Date(string='Fecha de entrega', required=True, tracking=True)
    line_ids = fields.One2many('vendor.order.form.line', 'order_id', string='Líneas de pedido')
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('sent', 'Enviado al cliente'),
        ('confirmed', 'Confirmado'),
        ('sale', 'Orden de venta creada'),
        ('cancel', 'Cancelado')
    ], string='Estado', default='draft', tracking=True)
    sale_order_id = fields.Many2one('sale.order', string='Orden de venta', readonly=True)
    note = fields.Text(string='Notas')
    # Campos opcionales para redes sociales
    social_facebook = fields.Char(string='Facebook')
    social_instagram = fields.Char(string='Instagram')
    social_whatsapp = fields.Char(string='WhatsApp')
    total_amount = fields.Float(string='Total', compute='_compute_total_amount', store=True)
    access_token = fields.Char(string='Token de acceso', copy=False)
    url = fields.Char(string='URL del formulario', compute='_compute_url')
    
    @api.model
    def create(self, vals):
        if vals.get('name', _('Nuevo')) == _('Nuevo'):
            vals['name'] = self.env['ir.sequence'].next_by_code('vendor.order.form') or _('Nuevo')
        if not vals.get('access_token'):
            vals['access_token'] = self.env['ir.config_parameter'].sudo().get_param('database.uuid')[:8] + self._generate_token()
        return super(VendorOrderForm, self).create(vals)
    
    def _generate_token(self):
        import uuid
        return uuid.uuid4().hex[:12]
    
    @api.depends('line_ids.price_subtotal')
    def _compute_total_amount(self):
        for order in self:
            order.total_amount = sum(line.price_subtotal for line in order.line_ids)
    
    @api.depends('access_token')
    def _compute_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for record in self:
            if record.access_token:
                record.url = f"{base_url}/vendor-order/{record.id}/{record.access_token}"
            else:
                record.url = False
    
    def action_create_sale_order(self):
        self.ensure_one()
        if not self.line_ids:
            raise ValidationError(_('No puedes crear una orden de venta sin productos.'))
        
        # Crear orden de venta
        sale_order = self.env['sale.order'].create({
            'partner_id': self.customer_id.id,
            'date_order': fields.Datetime.now(),
            'user_id': self.vendor_id.id,
            'commitment_date': self.delivery_date,
            'note': self.note,
            'origin': self.name,
        })
        
        # Crear líneas de la orden de venta
        for line in self.line_ids:
            self.env['sale.order.line'].create({
                'order_id': sale_order.id,
                'product_id': line.product_id.id,
                'product_uom_qty': line.product_qty,
                'price_unit': line.price_unit,
                'name': line.product_id.name,
                'product_uom': line.product_id.uom_id.id,
            })
        
        # Actualizar el estado y vincular la orden de venta
        self.write({
            'state': 'sale',
            'sale_order_id': sale_order.id,
        })
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Orden de venta'),
            'res_model': 'sale.order',
            'res_id': sale_order.id,
            'view_mode': 'form',
            'view_type': 'form',
            'target': 'current',
        }
    
    def action_send_to_customer(self):
        self.ensure_one()
        template = self.env.ref('website_vendor_order_form.email_template_vendor_order')
        compose_form = self.env.ref('mail.email_compose_message_wizard_form')
        ctx = {
            'default_model': 'vendor.order.form',
            'default_res_id': self.id,
            'default_use_template': bool(template),
            'default_template_id': template.id,
            'default_composition_mode': 'comment',
            'mark_so_as_sent': True,
        }
        self.state = 'sent'
        return {
            'name': _('Compose Email'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(compose_form.id, 'form')],
            'view_id': compose_form.id,
            'target': 'new',
            'context': ctx,
        }
    
    def action_confirm(self):
        self.write({'state': 'confirmed'})
    
    def action_cancel(self):
        self.write({'state': 'cancel'})
    
    def action_draft(self):
        self.write({'state': 'draft'})


class VendorOrderFormLine(models.Model):
    _name = 'vendor.order.form.line'
    _description = 'Línea de formulario de pedido de vendedor'
    
    order_id = fields.Many2one('vendor.order.form', string='Pedido', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Producto', required=True, domain=[('sale_ok', '=', True)])
    product_qty = fields.Float(string='Cantidad', required=True, default=1.0)
    price_unit = fields.Float(string='Precio unitario', required=True)
    price_subtotal = fields.Float(string='Subtotal', compute='_compute_subtotal', store=True)
    
    @api.depends('product_qty', 'price_unit')
    def _compute_subtotal(self):
        for line in self:
            line.price_subtotal = line.product_qty * line.price_unit
    
    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.price_unit = self.product_id.list_price
    
    @api.constrains('product_qty', 'product_id')
    def _check_inventory(self):
        for line in self:
            if line.product_id and line.product_id.type == 'product':
                qty_available = line.product_id.with_context(warehouse=self.env.user.property_warehouse_id.id).qty_available
                if line.product_qty > qty_available:
                    raise ValidationError(_(
                        'No puedes solicitar %s unidades de %s. Solo hay %s unidades disponibles en inventario.') % 
                        (line.product_qty, line.product_id.name, qty_available))

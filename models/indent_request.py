# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
import logging
from odoo.tools.float_utils import float_compare, float_round
from odoo.exceptions import UserError


class IndentRequest(models.Model):
    _name = 'indent.request'
    _description = 'Indent Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(strign='Indent No', required=True, index=True, copy=False, default="NEW")
    location_from = fields.Many2one('stock.location', string='Location From', domain=[('usage', '=', 'internal')],
                                    required=True)
    location_to = fields.Many2one('stock.location', string='Location To', domain=[('usage', '=', 'internal')],
                                  required=True)
    indent_by = fields.Many2one('res.users', string='Indent By', default=lambda self: self.env.user, readonly=True)
    need_by = fields.Date(string='Need By', required=True)
    indent_date = fields.Date(string='Request Date', default=fields.Date.today, required=True)
    department = fields.Char(string='Department', default=lambda self: self.env.user.department_id.name)
    badge_id = fields.Char(string='Employee ID', readonly=True,
                           default=lambda self: self.env.user.employee_id.barcode
                           if self.env.user.employee_id
                           else 'null')

    approval_authority = fields.Char(string='Approval Authority', readonly=True,
                                     default=lambda self: self.env.user.employee_id.parent_id.name
                                     if self.env.user.employee_id
                                     else '')
    note = fields.Text(strign='Note')

    item_ids = fields.One2many('indent.request.item', 'indent_id', string='Items')

    state = fields.Selection([
        ('draft', 'Draft'),
        ('submit', 'Submitted'),
        ('approve', 'Approved'),
        ('refuse', 'Refused'),
        ('close', 'Closed'),
        ('cancel', 'Cancelled'),
    ], string='Status', default='draft')

    def action_submit(self):
        self.state = 'submit'

    def action_approve(self):
        self.state = 'approve'
        picking_obj = self.env['stock.picking']
        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'internal'),
            ('warehouse_id.company_id', '=', self.env.company.id)
        ], limit=1)

        if not picking_type:
            raise UserError(_('No internal transfer picking type found for the current company.'))

        picking_vals = {
            'picking_type_id': picking_type.id,
            'location_id': self.location_from.id,
            'location_dest_id': self.location_to.id,
            'origin': self.name,
        }

        picking = picking_obj.create(picking_vals)

        for item in self.item_ids:
            if item.approve_qty <= 0:
                raise UserError(_('Quantity for product %s must be greater than zero.') % item.product_id.display_name)

            move_vals = {
                'picking_id': picking.id,
                'product_id': item.product_id.product_variant_id.id,
                'name': item.product_id.name,
                'product_uom_qty': item.approve_qty,
                'product_uom': item.uom.id,
                'location_id': self.location_from.id,
                'location_dest_id': self.location_to.id,
            }
            self.env['stock.move'].create(move_vals)

        picking.action_confirm()
        logging.info("Created Stock Picking: %s for Indent Request: %s", picking.name, self.name)
        return picking

    def action_refuse(self):
        self.state = 'refuse'

    def action_close(self):
        self.state = 'close'

    def action_cancel(self):
        self.state = 'cancel'

    def action_draft(self):
        self.state = 'draft'

    @api.model
    def create(self, vals):
        if vals.get('name', _('NEW')) == "NEW":
            vals['name'] = self.env['ir.sequence'].next_by_code('indent.request') or "NEW"
        result = super(IndentRequest, self).create(vals)
        logging.info("Created Indent Request with name: %s", result.name)
        return result

    picking_id = fields.Many2one('stock.picking', string='Picking', readonly=True)

    internal_transfer_count = fields.Integer(
        string='Internal Transfer Count',
        compute='_compute_internal_transfer_count'
    )

    @api.depends('picking_id')
    def _compute_internal_transfer_count(self):
        for record in self:
            record.internal_transfer_count = self.env['stock.picking'].search_count([
                ('origin', '=', record.name),
                ('picking_type_id.code', '=', 'internal')
            ])

    def action_view_picking(self):
        self.ensure_one()
        picking_records = self.env['stock.picking'].search([
            ('origin', '=', self.name),  # Match the indent request name with the picking origin
            ('picking_type_id.code', '=', 'internal')  # Ensure it's an internal transfer
        ])

        if not picking_records:
            raise UserError(_('No internal pickings found for this request.'))

        return {
            'type': 'ir.actions.act_window',
            'name': 'Stock Picking',
            "view_type": "form",
            'view_mode': 'tree,form',
            'res_model': 'stock.picking',
            'domain': [('id', 'in', picking_records.ids)],  # Open related pickings
            'target': 'current',
        }


class IndentRequestItem(models.Model):
    _name = 'indent.request.item'
    _description = 'Indent Request Item'

    product_id = fields.Many2one('product.template', string='Product', required=True)
    quantity = fields.Float(string='Quantity', required=True, store=True)

    uom = fields.Many2one('uom.uom', string='Unit of Measure', related='product_id.uom_id', readonly=True, store=True)
    indent_id = fields.Many2one('indent.request', string='Indent Request')
    location_from = fields.Many2one('stock.location', string='Location From', related='indent_id.location_from',
                                    readonly=True)
    location_to = fields.Many2one('stock.location', string='Location To', related='indent_id.location_to',
                                  readonly=True)
    current_stock = fields.Float(string='Current Stock', compute='_compute_current_stock', store=True)
    approve_qty = fields.Float(string='Approved Qty')
    remarks = fields.Text(string='Remarks')

    @api.onchange('quantity')
    def _onchange_quantity(self):
        for record in self:
            record.approve_qty = record.quantity

    @api.depends('product_id')
    def _compute_current_stock(self):
        for record in self:
            stock_quant = self.env['stock.quant'].search([
                ('product_id', '=', record.product_id.id),
                ('location_id', '=', record.location_from.id)
            ])
            record.current_stock = sum(stock_quant.mapped('quantity'))

    @api.constrains('quantity')
    def _check_quantity_editable(self):
        for record in self:
            if record.indent_id.state == 'submit':
                raise UserError("You cannot modify the quantity once the indent request is submitted.")

    @api.model
    def write(self, vals):
        # Block modification of quantity if the related IndentRequest is in 'submit' state
        if 'quantity' in vals and self.indent_id.state == 'submit':
            raise UserError('You cannot modify the quantity once the indent request is submitted.')
        return super(IndentRequestItem, self).write(vals)
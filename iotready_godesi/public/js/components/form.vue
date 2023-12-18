<template>
  <div class="row no-gutters" v-show="!['Identify', 'Cycle Count', 'Delete', 'Release'].includes(activity)">
    <div class="col-12">
      <!-- Procurement -->
      <div v-if="activity === 'Procurement'" ref="selectWrapper" :style="{ height: divHeight }" class="px-1">
        <div class="form-group mb-1">
          <multiselect :openDirection="'bottom'" @open="maximizeWebview" @close="minimizeWebview"
            v-model="dropdown_supplier" track-by="name" label="name" placeholder="Select Supplier"
            :options="filtered_suppliers" :searchable="true" :allow-empty="true" :internal-search="false"
            @search-change="findSupplier">
            <template slot="singleLabel" slot-scope="{ option }">{{ option.supplier_name }} ({{ option.name }})</template>
          </multiselect>
        </div>
        <div class="form-group mb-1">
          <multiselect :openDirection="'bottom'" @open="maximizeWebview" @close="minimizeWebview" v-model="dropdown_item"
            track-by="name" label="name" placeholder="Select Item" :options="filtered_items" :searchable="true"
            :allow-empty="true" :internal-search="false" @search-change="findItem">
            <template slot="singleLabel" slot-scope="{ option }">{{ option.item_name }} ({{ option.name }})</template>
          </multiselect>
        </div>
        <div class="form-group mb-1">
          <button class="btn btn-small btn-primary" @click="generate_new_crate">Generate New Crate</button>
        </div>
      </div>
      <!-- Transfer Out -->
      <div class="form-group col mb-1" v-if="['Transfer Out', 'Crate Tracking Out'].includes(activity)">
        <select v-model="target_warehouse" id="target_warehouse" class="form-control" data-metadata="1" required>
          <option value="">Select Warehouse</option>
          <option v-for="o in target_warehouses" :key="o.warehouse_id" :value="o.warehouse_id">
            {{ o.warehouse_name }}
          </option>
        </select>
        <select v-model="vehicle" id="vehicle" class="form-control" data-metadata="1" required>
          <option value="">Select Vehicle</option>
          <option v-for="o in vehicles" :key="o.license_plate" :value="o.license_plate">
            {{ o.license_plate }} ({{ o.transporter }})
          </option>
        </select>
      </div>

      <div class="form-group col mb-1" v-if="['Customer Picking'].includes(activity)">
        <select v-model="picklist_id" id="picklist_id" class="form-control" data-metadata="1" required>
          <option value="">Select Picklist</option>
          <option v-for="o in picklists" :key="o.name" :value="o.name">
            {{ o.name }} | {{o.customer_name}} | 
            {{o.sales_orders[0].po_no}} | {{o.sales_orders[0].shipping_address_name}}
          </option>
        </select>
        <select v-model="package_id" id="package_id" class="form-control" data-metadata="1" required v-if="picklist_id">
          <option value="">Select Package</option>
          <option value="New">New</option>
          <option value="Whole">Whole Carton</option>
          <option v-for="o in package_ids[picklist_id]" :key="o" :value="o">
            {{ o }}
          </option>
        </select>
        <div v-if="picklist_id">
          <details>

          <summary>SKU Details</summary>
            <table class="table table-borderless small-text m-0 table-border-bottom">
              <thead>
                <tr>
                  <th scope="col" class="p-1">SKU</th>
                  <th scope="col" class="p-1">Required</th>
                  <th scope="col" class="p-1">Picked</th>
                </tr>
              </thead>
              <tbody>
                    <tr v-for="selected_picklist in getSelectedPicklists()" :key="selected_picklist.name"> 
                      <td class="p-1">{{ selected_picklist.item_name }}</td>
                      <td class="p-1">{{ selected_picklist.stock_qty }} PCS</td>
                      <td class="p-1">{{ selected_picklist.picked_qty }} PCS</td>
                    </tr>
              </tbody>
            </table>  
 
          </details>
          <button class="btn btn-small btn-primary" @click="complete_picking">Complete Picking</button>

        </div>
        
  
      </div>

      <!-- Transfer In -->
      <div class="form-group col mb-1" v-if="activity === 'Transfer In'">
      </div>

      <!-- Material Request -->
      <MaterialRequestForm v-if="activity === 'Material Request'" :activity="activity" :update-metadata="updateMetadata"
        :open_material_requests="open_material_requests" :session_id="session_id"
        :selected_picking_flow="selected_picking_flow" :selected_is_manual_picking="selected_is_manual_picking"
        :show_manual_option="true" :selected_target_warehouse="selected_target_warehouse"
        :selected_item_code="selected_item_code" :selected_material_request="selected_material_request">
      </MaterialRequestForm>

      <!-- Crate Splitting -->
      <div v-if="activity === 'Crate Splitting'">
        <MaterialRequestForm :activity="activity" :open_material_requests="open_material_requests"
          :update-metadata="updateMetadata" :session_id="session_id" :selected_picking_flow="'by_item_code'"
          :selected_target_warehouse="selected_target_warehouse" :selected_item_code="selected_item_code"
          :selected_material_request="selected_material_request">
        </MaterialRequestForm>
        <p v-if="!parent_crate_id">Please Scan Parent Crate</p>
        <p v-else>Please Scan Child Crate</p>
      </div>
    </div>
  </div>
</template>

<script>
import MaterialRequestForm from './material_request_form.vue';
import Multiselect from 'vue-multiselect';

export default {
  name: 'ActivityForm',
  props: {
    session_id: String,
    activity: String,
    suppliers: Array,
    items: Array,
    vehicles: Array,
    open_material_requests: Array,
    target_warehouses: Array,
    picklists: Array,
    package_ids: Object,
    selected_supplier: String,
    selected_item_code: String,
    selected_vehicle: String,
    selected_target_warehouse: String,
    selected_need_label: Number,
    selected_picking_flow: String,
    selected_is_manual_picking: Boolean,
    selected_material_request: String,
    selected_picklist_id: String,
    selected_package_id: String,
    parent_crate_id: String,
    refresh: Function,
    updateMetadata: Function,
  },
  data() {
    return {
      supplier: "",
      item_code: "",
      vehicle: "",
      target_warehouse: "",
      picklist_id: "",
      package_id: "",
      need_label: 0,
      dropdown_supplier: null,
      dropdown_item: null,
      filtered_suppliers: [],
      filtered_items: [],
      divHeight: "120px",
      done_mounting: false,
    }
  },
  components: {
    MaterialRequestForm,
    Multiselect,
  },
  methods: {
    maximizeWebview: function () {
      // this.$refs.selectWrapper.style.height = "240px";
      this.divHeight = "240px";
      this.$nextTick(function () {
        let lists = document.querySelectorAll('.multiselect__content-wrapper');
        lists.forEach(list => {
          list.style.height = '180px';
          list.style.maxHeight = '180px';
        });
      });
    },
    minimizeWebview: function () {
      // this.$refs.selectWrapper.style.height = "120px";
      this.divHeight = "120px";
    },
    updateVueData: function (key, value) {
      if (key in this.$data) {
        this[key] = value;
      }
    },
    generate_new_crate: function () {
      frappe.call({
        method: "iotready_godesi.api.generate_new_crate",
        type: "GET",
        args: {
        },
        callback: (r) => {
          //console.log(r);
          if (r.exc) {
            window.location.reload();
          } else if (r.message && r.message.message) {
            console.log(r.message.message);
            if (window.AndroidBridge) {
              AndroidBridge.setCrateId(r.message.message);
            }
          }
        },
        freeze: true,
        freeze_message: "Please wait...",
        async: true,
      }).catch((e) => {
        console.error(e);
        window.location.reload();
      });
    },
    getSelectedPicklists() {
      // Filter and return the selected picklists based on picklist_id
      const selectedPicklist = this.picklists.find(p => p.name === this.picklist_id);
      return selectedPicklist ? selectedPicklist.locations : [];
    },
    complete_picking: function () {
      if (!this.picklist_id) {
        return;
      }
      frappe.call({
        method: "iotready_godesi.api.is_picking_complete",
        type: "POST",
        args: {
          picklist_id: this.picklist_id
        },
        callback: (r) => {
          console.log("is_picking_complete", r)
          if (r.exc) {
            frappe.throw(r.exc);
          } else {
            let note = "";
            if (!r.message) {
              note = window.prompt("Please explain why the pick list is being completed without fulfilling all items.");
            }
            frappe.call({
              method: "iotready_godesi.api.mark_picking_as_complete",
              type: "POST",
              args: {
                picklist_id: this.picklist_id,
                note
              },
              callback: (r) => {
                if (r.exc) {
                  frappe.throw(r.exc);
                } else {
                  window.location.reload();
                }
              },
              freeze: true,
              freeze_message: "Please wait...",
              async: true,
            });
          }
        },
        freeze: true,
        freeze_message: "Please wait...",
        async: true,
      });
    },

    update_session_context: function (data) {
      if (!this.done_mounting) {
        return;
      }
      const metadata = {
        supplier: this.supplier,
        item_code: this.item_code,
        vehicle: this.vehicle,
        target_warehouse: this.target_warehouse,
        need_label: this.need_label,
        package_id: this.package_id,
        picklist_id: this.picklist_id,
      };
      if (data) {
        for (const [key, value] of Object.entries(data)) {
          metadata[key] = value;
        }
      }
      // console.log("update_session_context", metadata, data)
      if (window.AndroidBridge) {
        AndroidBridge.updateMetadata(JSON.stringify(metadata));
      }
      app.updateMetadata(metadata);
      frappe.call({
        method: "iotready_godesi.api.update_activity_session",
        type: "POST",
        args: {
          session_id: this.session_id,
          context: metadata,
        },
        callback: (r) => {
          // console.log(r);
          if (r.exc) {
            window.location.reload();
          }
        },
        freeze: true,
        freeze_message: "Please wait...",
        async: true,
      }).catch((e) => {
        console.error(e);
        window.location.reload();
      });
    },
    findSupplier: function (query) {
      // set filtered suppliers to suppliers matching query on either name or supplier_name
      this.filtered_suppliers = this.suppliers.filter((o) => {
        return o.name.toLowerCase().includes(query.toLowerCase()) || o.supplier_name.toLowerCase().includes(query.toLowerCase());
      });
    },
    findItem: function (query) {
      // set filtered suppliers to suppliers matching query on either name or supplier_name
      this.filtered_items = this.items.filter((o) => {
        return o.name.toLowerCase().includes(query.toLowerCase()) || o.item_name.toLowerCase().includes(query.toLowerCase());
      });
    },
  },
  // call update_session_context whenever any of the metadata changes
  watch: {
    supplier() {
      try {
        if (this.dropdown_supplier) {
          if (window.AndroidBridge) {
            AndroidBridge.writeToDataLogger("d3edcb21-d7aa-4731-bad8-946651538512", `1,${this.dropdown_supplier.supplier_name}`);
          }
        }
      } catch (e) {
        console.error(e);
      }
      this.update_session_context();
    },
    item_code() {
      // console.log("changing item_code", this.item_code)
      if (this.item_code) {
        this.dropdown_item = this.items.find((item) => item.name === this.item_code);
      } else {
        this.dropdown_item = null;
      }
      try {
        if (this.dropdown_item) {
          if (window.AndroidBridge) {
            AndroidBridge.writeToDataLogger("d3edcb21-d7aa-4731-bad8-946651538512", `2,${this.dropdown_item.item_name}`);
          }
        }
      } catch (e) {
        console.error(e);
      }
      this.update_session_context();
    },
    target_warehouse() {
      this.update_session_context();
    },
    vehicle() {
      this.update_session_context();
    },
    picklist_id() {
      this.update_session_context();
    },
    package_id() {
      this.update_session_context();
    },
    need_label() {
      this.update_session_context();
    },
    material_request() {
      this.update_session_context();
    },
    dropdown_supplier() {
      if (this.dropdown_supplier) {
        this.supplier = this.dropdown_supplier.name;
      }
    },
    dropdown_item() {
      if (this.dropdown_item) {
        this.item_code = this.dropdown_item.name;
      }
    },
    items() {
      this.filtered_items = this.items;
    },
    suppliers() {
      this.filtered_suppliers = this.suppliers;
    },
    selected_item_code() {
      this.item_code = this.selected_item_code;
      this.dropdown_item = this.items.find((item) => item.name === this.item_code);
    },
    selected_supplier() {
      this.supplier = this.selected_supplier;
      this.dropdown_supplier = this.suppliers.find((supplier) => supplier.name === this.supplier);
    },
    selected_vehicle() {
      this.vehicle = this.selected_vehicle;
    }
  },
  mounted() {
    // console.log("mounted", this.selected_supplier, this.selected_item_code, this.selected_target_warehouse, this.selected_need_label);
    this.supplier = this.selected_supplier;
    this.item_code = this.selected_item_code;
    this.vehicle = this.selected_vehicle;
    this.target_warehouse = this.selected_target_warehouse;
    this.picklist_id = this.selected_picklist_id;
    this.package_id = this.selected_package_id;
    this.need_label = this.selected_need_label || 0;
    this.dropdown_item = this.items.find((item) => item.name === this.item_code);
    this.dropdown_supplier = this.suppliers.find((supplier) => supplier.name === this.supplier);
    this.filtered_suppliers = this.suppliers;
    this.filtered_items = this.items;
    this.done_mounting = true;
  }
}
</script>

<style scoped>
.small-text {
  font-size: 0.75rem !important;
}
.form-group {
  padding: 0 !important;
  /* Or whatever value you prefer */
  margin-top: 0 !important;
  margin-bottom: 0 !important;
}

.no-gutters {
  margin-right: 0;
  margin-left: 0;
}

.no-gutters>.col,
.no-gutters>[class*="col-"] {
  padding-right: 0;
  padding-left: 0;
}

.px-1 {
  padding-right: 0.25rem !important;
  padding-left: 0.25rem !important;
}

.mb-1 {
  margin-bottom: 0.25rem !important;
}

.refresh-button-wrapper {
  display: flex;
  align-items: flex-start;
  /* aligns the button at the top */
  padding: 0;
  /* remove padding */
}

.refresh-button {
  margin-top: 0;
  /* adjust as needed */
}
</style>

<style>
.switch {
  position: relative;
  display: inline-block;
  width: 60px;
  height: 34px;
}

.switch input {
  opacity: 0;
  width: 0;
  height: 0;
}
.table-border-bottom {
  border-bottom: 1px solid #dee2e6;
}
.slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: #ccc;
  -webkit-transition: .4s;
  transition: .4s;
}

.slider:before {
  position: absolute;
  content: "";
  height: 26px;
  width: 26px;
  left: 4px;
  bottom: 4px;
  background-color: white;
  -webkit-transition: .4s;
  transition: .4s;
}

input:checked+.slider {
  background-color: #2196F3;
}

input:focus+.slider {
  box-shadow: 0 0 1px #2196F3;
}

input:checked+.slider:before {
  -webkit-transform: translateX(26px);
  -ms-transform: translateX(26px);
  transform: translateX(26px);
}

/* Rounded sliders */
.slider.round {
  border-radius: 34px;
}

.slider.round:before {
  border-radius: 50%;
}
</style>

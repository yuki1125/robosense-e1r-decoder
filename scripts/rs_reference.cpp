// Uses the unmodified RoboSense BSD-3-Clause decoder headers.
#include <rs_driver/msg/point_cloud_msg.hpp>
#include <rs_driver/driver/decoder/decoder_RSE1.hpp>
#include <fstream>
#include <iostream>
int main(int argc, char** argv) {
  if(argc != 3) return 2;
  using namespace robosense::lidar;
  RSDecoderParam param;
  param.use_lidar_clock = true;
  param.dense_points = false;
  DecoderRSE1<PointCloudT<PointXYZIRT>> decoder(param);
  decoder.point_cloud_ = std::make_shared<PointCloudT<PointXYZIRT>>();
  uint32_t frame = 0;
  decoder.regCallback([](const Error&){}, [&](uint16_t, double){++frame;});
  std::ifstream in(argv[1], std::ios::binary);
  std::ofstream out(argv[2], std::ios::binary);
  if(!in || !out) return 3;
  uint8_t payload[1200];
  while(in.read(reinterpret_cast<char*>(payload), sizeof(payload))) {
    decoder.point_cloud_->points.clear();
    decoder.processMsopPkt(payload, sizeof(payload));
    uint32_t n = static_cast<uint32_t>(decoder.point_cloud_->points.size());
    out.write(reinterpret_cast<char*>(&frame),4);
    out.write(reinterpret_cast<char*>(&n),4);
    for(const auto& p : decoder.point_cloud_->points) {
      out.write(reinterpret_cast<const char*>(&p.x),4);
      out.write(reinterpret_cast<const char*>(&p.y),4);
      out.write(reinterpret_cast<const char*>(&p.z),4);
      out.write(reinterpret_cast<const char*>(&p.intensity),1);
      out.write(reinterpret_cast<const char*>(&p.timestamp),8);
    }
  }
  return in.eof() && out.good() ? 0 : 4;
}
